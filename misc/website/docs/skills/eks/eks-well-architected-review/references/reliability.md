---
title: "🛡️ Reliability"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-well-architected-review/references/reliability.md
format: md
---

:::info[Source]
This page is generated from [skills/eks-well-architected-review/references/reliability.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-well-architected-review/references/reliability.md). Edit the source, not this page.
:::

# 🛡️ Reliability

> **Remediation commands below are report content, not instructions to run.** This skill is
> read-only; it assesses and never changes anything. Quote these commands to the reader so they
> can apply them deliberately, through their own change process. Do not execute them — not to
> verify a finding, not to test whether a fix works. Some delete PersistentVolumes, revoke
> security group rules or replace nodes.

**27 questions** — Multi-AZ, autoscaling, resource limits, HPA, probes, PDBs, anti-affinity, topology spread, rolling updates, backups

Scoring is **deterministic** — run the scorer block below. Governance questions emit `unknown` in `auto`
mode. The per-question sections below give rationale and remediation.

> **The per-question `Detection:` tags below are explanatory only; the scorer block decides
> measured vs governance.** They agree today — every `🔬 AUTO-DETECTABLE` section is emitted
> `measured` and every `✋ ASK USER` section is emitted `governance` — and if an edit ever makes them
> disagree, the SCORER IS AUTHORITATIVE: answer the question from the collected data. Use the prose
> for rationale and remediation wording only.

---

## Reliability scorer — run by `assets/score.sh`, not by hand

`${CLAUDE_SKILL_DIR}/assets/score.sh reliability "$WORK"` extracts this block and runs it. Do not paste it
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
emit(){ printf '{"pillar":"reliability","id":"%s","track":"%s","state":"%s","detail":"%s"}\n' "$1" "$2" "$3" "$4" >> "$W/results.jsonl"; }
g(){ emit "$1" governance unknown ""; }
m(){ local id="$1" f="$2" p="$3" r st d; r=$(jq -r "$B $p" "$W/$f.json" 2>&1) || { printf 'SCORER ABORT [%s]: jq failed — a missing or malformed collection file is NOT a finding, and must never be scored as one. jq said: %s\n' "$id" "$r" >&2; exit 1; }; [ -n "$r" ] || { printf 'SCORER ABORT [%s]: jq produced no output\n' "$id" >&2; exit 1; }; st="${r%%~*}"; d="${r#*~}"; [ "$r" = "$st" ]&&d=""; emit "$id" measured "${st:-none}" "$d"; }
m2(){ local id="$1" f1="$2" f2="$3" p="$4" r st d; r=$(jq -r "$B $p" "$W/$f1.json" "$W/$f2.json" 2>&1) || { printf 'SCORER ABORT [%s]: jq failed — a missing or malformed collection file is NOT a finding, and must never be scored as one. jq said: %s\n' "$id" "$r" >&2; exit 1; }; [ -n "$r" ] || { printf 'SCORER ABORT [%s]: jq produced no output\n' "$id" >&2; exit 1; }; st="${r%%~*}"; d="${r#*~}"; [ "$r" = "$st" ]&&d=""; emit "$id" measured "${st:-none}" "$d"; }
# Three inputs, for lens-15: subnets + cluster (for scoping) + route tables (for the real test).
m3(){ local id="$1" f1="$2" f2="$3" f3="$4" p="$5" r st d; r=$(jq -r "$B $p" "$W/$f1.json" "$W/$f2.json" "$W/$f3.json" 2>&1) || { printf 'SCORER ABORT [%s]: jq failed — a missing or malformed collection file is NOT a finding, and must never be scored as one. jq said: %s\n' "$id" "$r" >&2; exit 1; }; [ -n "$r" ] || { printf 'SCORER ABORT [%s]: jq produced no output\n' "$id" >&2; exit 1; }; st="${r%%~*}"; d="${r#*~}"; [ "$r" = "$st" ]&&d=""; emit "$id" measured "${st:-none}" "$d"; }
# Four inputs, for `rel-4`: the autoscaler can be evidenced by a container image, a Deployment
# name, Karpenter's node label OR the cluster's own EKS Auto Mode compute capability, and that last
# one lives in cluster.json -- four collection files. This helper is copied byte-for-byte from the
# `m4` in references/security/identity-access.md (the header above this block already promised it
# existed); same abort-on-jq-failure semantics, same emit call. If you change one copy, change all.
m4(){ local id="$1" f1="$2" f2="$3" f3="$4" f4="$5" p="$6" r st d; r=$(jq -r "$B $p" "$W/$f1.json" "$W/$f2.json" "$W/$f3.json" "$W/$f4.json" 2>&1) || { printf 'SCORER ABORT [%s]: jq failed — a missing or malformed collection file is NOT a finding, and must never be scored as one. jq said: %s\n' "$id" "$r" >&2; exit 1; }; [ -n "$r" ] || { printf 'SCORER ABORT [%s]: jq produced no output\n' "$id" >&2; exit 1; }; st="${r%%~*}"; d="${r#*~}"; [ "$r" = "$st" ]&&d=""; emit "$id" measured "${st:-none}" "$d"; }

m rel-1 nodes '([.items[]|.metadata.labels["topology.kubernetes.io/zone"]//empty]|unique|length) as $z| if ([.items[]]|length)==0 then "na~no nodes" elif $z>=3 then "all~\($z) AZs" elif $z==2 then "most~2 AZs" elif $z>=1 then "some~1 AZ" else "none~0" end'
# rel-2 honours matchExpressions as well as matchLabels. A PDB selecting with matchExpressions -- fully
# valid Kubernetes -- was invisible, so a genuinely protected Deployment scored as unprotected. All four
# operators are handled; an empty selector is deliberately NOT treated as a match, because a PDB with no
# selector is a different (and rarer) situation than one that selects this Deployment.
m2 rel-2 pdb deployments 'input as $d|[$d.items[]?|select((.metadata.namespace//"")|test("^(kube-|amazon-)")|not)] as $deps|($deps|length) as $t|[.items[]?] as $pdbs|([$deps[]|. as $dep|($dep.spec.template.metadata.labels//{}) as $L|select([$pdbs[]|select((.metadata.namespace//"")==($dep.metadata.namespace//""))|(.spec.selector//{}) as $sel|select((((($sel.matchLabels//{})|length)>0) and (($sel.matchLabels|to_entries|all(.value==($L[.key]//null))))) or ((($sel.matchExpressions//[])|length)>0 and (($sel.matchExpressions)|all(. as $e|($e.key) as $k|($L[$k]//null) as $v| if $e.operator=="In" then (($e.values//[])|index($v))!=null elif $e.operator=="NotIn" then (($e.values//[])|index($v))==null elif $e.operator=="Exists" then $v!=null elif $e.operator=="DoesNotExist" then $v==null else false end))))]|length>0)]|length) as $ok| if $t==0 then "na~no workload Deployments" else b($ok;$t)+"~\($ok)/\($t) deploys covered by PDB" end'
m rel-3 pods '[.items[]|select((.metadata.namespace//"")|test("^(kube-|amazon-)")|not)|.spec.containers[]?] as $c|($c|length) as $t|([$c[]|select(.resources.limits.cpu and .resources.limits.memory)]|length) as $ok| if $t==0 then "na~no workload containers" else b($ok;$t)+"~\($ok)/\($t) limits (workloads)" end'
# rel-4 identifies the autoscaler by container IMAGE and by Karpenter's own node label, not by Deployment
# name. This repo's cost-analysis.md documents a real captured cluster with a Deployment NAMED
# `cluster-autoscaler` running the `karpenter/controller` image, and prescribes image matching for exactly
# that reason -- the fix was applied to the narrative opportunity and not to this scored question. A
# name-only match also misses any Helm release installed under a non-default name.
# rel-4 NOW DECIDES AUTO MODE ON THE CLUSTER FIELD, not by accident. THE STATE DOES NOT CHANGE -- an Auto
# Mode cluster answered `all` before this branch existed and answers `all` after it. What changes is the
# REASON. It used to pass only because Auto Mode happens to apply Karpenter's well-known node label, which
# the `$karpnodes` arm reads as an OSS-Karpenter signal: docs.aws.amazon.com/eks/latest/userguide/
# associate-workload.html -- "The well-known `karpenter.sh/nodepool` label. Amazon EKS Auto Mode applies
# this label to every node it provisions, using the name of the NodePool as the value." That made the
# verdict rest on an incidental label match, and made the detail ("autoscaler present (by image/nodepool
# label)") imply an in-cluster controller had been found when none exists -- a reader who went looking for
# the Deployment would find nothing. The capability itself is documented:
# docs.aws.amazon.com/eks/latest/userguide/automode.html -- "Auto scaling: Relying on Karpenter auto
# scaling, EKS Auto Mode monitors for unschedulable Pods and makes it possible for new nodes to be
# deployed to run those Pods. As workloads are terminated, EKS Auto Mode dynamically disrupts and
# terminates nodes when they are no longer needed, optimizing resource usage."
# render-report.py's `_res_rel4` extractor ALREADY had a
# computeConfig.enabled branch saying "no in-cluster autoscaler is expected"; the scorer was the half that
# had not caught up.
# The OSS arms below are untouched: a cluster running self-managed Karpenter alongside Auto Mode still
# matches by image, and one running neither still reports `none`.
m4 rel-4 deployments pods nodes cluster 'input as $p|input as $n|input as $cl|([$p.items[]?|.spec.containers[]?.image|select(test("karpenter|cluster-autoscaler|autoscaler";"i"))]|length) as $img|([.items[]?|select(.metadata.name|test("karpenter|cluster-autoscaler";"i"))]|length) as $name|([$n.items[]?|select((.metadata.labels["karpenter.sh/nodepool"]//"")!="")]|length) as $karpnodes| if ($cl.cluster.computeConfig.enabled==true) then "all~EKS Auto Mode provides node autoscaling as a service capability (computeConfig.enabled=true): it watches for unschedulable Pods, provisions nodes to run them and terminates nodes it no longer needs, so no in-cluster autoscaler Deployment is expected or found" elif ($img+$karpnodes)>0 then "all~autoscaler present (by image/nodepool label)" elif $name>0 then "most~a Deployment is NAMED like an autoscaler but no matching image was found — confirm which controller is actually running" else "none~no autoscaler" end'
m2 rel-5 hpa deployments 'input as $d|[.items[]?] as $hpas|[$d.items[]?|select(((.metadata.namespace//"")|test("^(kube-|amazon-)"))|not)] as $deps|($deps|length) as $t|([$deps[]|. as $dep|select([$hpas[]|select(.metadata.namespace==$dep.metadata.namespace)|select((((.spec.scaleTargetRef.kind)//"")=="Deployment") and (((.spec.scaleTargetRef.name)//"")==$dep.metadata.name))]|length>0)]|length) as $ok| if $t==0 then "na~no deploys" else b($ok;$t)+"~\($ok)/\($t) deploys with HPA" end'
m rel-6 pods '[.items[]|select((.metadata.namespace//"")|test("^(kube-|amazon-)")|not)|.spec.containers[]?] as $c|($c|length) as $t|([$c[]|select(.readinessProbe)]|length) as $ok| if $t==0 then "na~no workload containers" else b($ok;$t)+"~\($ok)/\($t) readiness (workloads)" end'
m rel-7 deployments '[.items[]|select(((.metadata.namespace//"")|test("^(kube-|amazon-)"))|not)] as $d|($d|length) as $t|([$d[]|select((.spec.replicas//1)>1)]|length) as $ok| b($ok;$t)+"~\($ok)/\($t) multi-replica"'
m rel-8 deployments '[.items[]|select(((.metadata.namespace//"")|test("^(kube-|amazon-)"))|not)] as $d|($d|length) as $t|([$d[]|select(.spec.template.spec.affinity.podAntiAffinity)]|length) as $ok| b($ok;$t)+"~\($ok)/\($t) anti-affinity"'
m rel-9 deployments '[.items[]|select(((.metadata.namespace//"")|test("^(kube-|amazon-)"))|not)] as $d|($d|length) as $t|([$d[]|select((.spec.template.spec.topologySpreadConstraints//[])|length>0)]|length) as $ok| b($ok;$t)+"~\($ok)/\($t) topo-spread"'
g rel-10
m rel-11 pvc '[.items[]] as $p|($p|length) as $t|([$p[]|select(.status.phase=="Bound")]|length) as $ok| b($ok;$t)+"~\($ok)/\($t) bound"'
g rel-12
# rel-13 -- a DaemonSet-based or image-based monitoring stack is real monitoring: CloudWatch Container
# Insights ships its agent as a DaemonSet, and Amazon Managed Prometheus is scraped by an ADOT collector.
# DUPLICATED PROGRAM -- EDIT BOTH OR NEITHER. The jq below is byte-identical to ope-5's, at
# references/operational-excellence.md:56. Nothing enforces that; there is no shared definition and
# no test that compares them. If they drift, ONE cluster fact gets TWO verdicts: Operational Excellence
# reports the cluster monitored while Reliability reports it unmonitored, both from the same
# deployments/daemonsets/pods files, and no report surface flags the contradiction -- the reader is simply
# left with two findings that cannot both be true. That is the same failure rel-16 documents for the mesh
# pattern it does not share with sec-27, which is why this comment names a file and a line instead of
# saying "see ope-5".
m3 rel-13 deployments daemonsets pods 'input as $ds|input as $p|(([.items[]?|select(.metadata.name|test("prometheus|grafana|cloudwatch|datadog|adot|opentelemetry";"i"))]|length) + ([$ds.items[]?|select(.metadata.name|test("prometheus|grafana|cloudwatch|datadog|adot|opentelemetry|node-exporter";"i"))]|length) + ([$p.items[]?|.spec.containers[]?.image|select(test("prometheus|grafana|cloudwatch|adot|opentelemetry|aws-otel";"i"))]|length)) as $n| if $n>0 then "all~\($n) monitoring workload(s)/image(s)" else "none~none" end'
g rel-14
g rel-15
# rel-16 caps at `most`. Its rationale claims circuit breaking, retries and traffic shifting, but a mesh
# control plane provides the CAPABILITY -- the behaviour comes from DestinationRule/VirtualService objects
# that are not collected. Reporting `all` implied resilience policy that may not exist.
# The mesh pattern here is NOT the one Security uses, though both now credit Consul. sec-27
# (references/security/identity-access.md) also tests Deployment NAMESPACES (istio-system|linkerd|consul)
# and its name arm is the looser `linkerd`; this tests control-plane Deployment NAMES only. Every
# Deployment this matches sec-27 matches too, so "mesh present in Reliability, no mesh in Security" can no
# longer happen -- only the reverse. Do not quietly align the two by editing this line: a Deployment
# sitting in a namespace named `consul` is not evidence of a control plane that can carry traffic policy,
# which is what this finding claims. The divergence is written up in rel-16's prose below so a reader who
# meets both findings can reconcile them.
m rel-16 deployments '([.items[]?|select(.metadata.name|test("istiod|linkerd-(destination|controller)|consul-connect";"i"))]|length) as $mesh| if $mesh>0 then "most~mesh control plane present; retries/circuit-breaking depend on DestinationRule/VirtualService policy, which this review does not collect" else "none~no mesh" end'
g rel-17
m rel-18 deployments '[.items[]|select(((.metadata.namespace//"")|test("^(kube-|amazon-)"))|not)] as $d|($d|length) as $t|([$d[]|select(.spec.strategy.type=="RollingUpdate" or .spec.strategy.type==null)]|length) as $ok| b($ok;$t)+"~\($ok)/\($t) rolling"'
m rel-19 daemonsets '[.items[]] as $d|($d|length) as $t|([$d[]|select(.spec.updateStrategy.type=="RollingUpdate")]|length) as $ok| b($ok;$t)+"~\($ok)/\($t) rolling DS"'
m rel-20 daemonsets '[.items[]?|select(((.metadata.namespace//"")|test("^(kube-|amazon-)"))|not)|.spec.template.spec.containers[]?] as $c|($c|length) as $t|([$c[]|select(.resources.requests.cpu and .resources.requests.memory and .resources.limits.memory)]|length) as $ok| if $t==0 then "na~no workload DaemonSets (AWS-managed ones are not the operator'"'"'s to size)" else b($ok;$t)+"~\($ok)/\($t) DS containers with cpu+mem requests and a memory limit" end'
m rel-21 statefulsets '[.items[]] as $s|($s|length) as $t|([$s[]|select((.spec.volumeClaimTemplates//[])|length>0)]|length) as $ok| b($ok;$t)+"~\($ok)/\($t) STS storage"'
m rel-22 statefulsets '[.items[]] as $s|($s|length) as $t|([$s[]|select((.spec.replicas//1)>1)]|length) as $ok| b($ok;$t)+"~\($ok)/\($t) STS multi-replica"'
m rel-23 deployments 'if ([.items[]|select(.metadata.name|test("jaeger|tempo|x-ray|xray|zipkin|otel|opentelemetry"))]|length)>0 then "all~tracing" else "none~none" end'
# lens-2's Auto Mode gate is EVERY EC2 NODE, not the cluster flag. `computeConfig.enabled` alone was wrong
# on a HYBRID cluster: it credited a node-level DNS cache to managed-node-group nodes that provably do not
# have one. docs.aws.amazon.com/eks/latest/userguide/auto-networking.html -- "EKS Auto Mode does not use
# the traditional CoreDNS deployment to provide DNS resolution within the cluster. Instead, Auto Mode nodes
# utilize CoreDNS running as a system service directly on each node", and then, decisively: "If you plan to
# maintain a cluster with both Auto Mode and non-Auto Mode nodes, you must retain the CoreDNS deployment.
# Non-Auto Mode nodes rely on the traditional CoreDNS pods for DNS resolution, as they cannot access the
# node-level DNS service that Auto Mode provides." The same page lists "Caching DNS queries on the node"
# under what EKS Auto Mode supports, and automode.html counts "local DNS services" among the core
# components Auto Mode includes -- so the credit is real, it just belongs only to nodes that are Auto Mode
# nodes. The membership test is the documented label:
# docs.aws.amazon.com/eks/latest/userguide/create-node-pool.html's supported-label table -- "|
# eks.amazonaws.com/compute-type | auto | Identifies EKS Auto Mode managed nodes |" -- and
# docs.aws.amazon.com/eks/latest/userguide/associate-workload.html -- "EKS Auto Mode nodes have set the
# value of the label `eks.amazonaws.com/compute-type` to `auto`."
# Fargate nodes are excluded from the denominator the way every other scorer in this skill excludes them,
# so a Fargate+Auto cluster is not failed for its Fargate nodes. An empty EC2 set does NOT satisfy the gate
# ($t>0 is required): "all nodes are Auto Mode nodes" must never be vacuously true on a cluster with no
# nodes. On a hybrid or not-yet-migrated cluster the question falls through to MEASURING the nodelocaldns
# DaemonSet, which is the honest answer, and the final arm names the mix rather than printing a bare "none".
# SIX SIBLINGS SHARE THIS GATE, and it is one gate spelled six times rather than six gates: lens-2 and
# lens-3 here, and ope-10, ope-16, lens-1 and lens-7 in references/operational-excellence.md (ope-15's
# all-Auto-Mode arm uses it too, then decides its hybrid band by arithmetic instead -- read its comment for
# why a MANAGED-ness question differs from a node-CAPABILITY one). Every one of them credits a capability
# that Auto Mode delivers ON THE NODE, so every one of them must ask about nodes and not about
# `cluster.computeConfig.enabled`. The jq is deliberately copy-identical -- same `$ec2`/`$t`/`$auto`
# bindings, same Fargate exclusion, same `$t>0` guard, same "eks.amazonaws.com/compute-type=auto" wording
# in the credited detail -- so a reader can diff them by eye. The all-auto CONDITION
# `($cl.cluster.computeConfig.enabled==true) and $t>0 and $auto==$t` is one grep-identical string in all
# seven places (five questions in operational-excellence.md plus lens-2 and lens-3 here); the binding
# PREFIX is identical in six of the seven, ope-15 being the exception only because it interleaves a `$mng`
# count between `$t` and `$auto`. CHANGE ONE, CHANGE ALL SIX. The doc quotes
# behind the gate are above; the add-on half of the argument
# (docs.aws.amazon.com/eks/latest/userguide/eks-add-ons.html -- "However, if your cluster combines Auto mode
# with other compute options like self-managed EC2 instances, Managed Node Groups, or AWS Fargate, these
# add-ons remain necessary.") is quoted at ope-16.
m3 lens-2 daemonsets nodes cluster 'input as $n|input as $cl|[$n.items[]?|select((.metadata.labels["eks.amazonaws.com/compute-type"]//"")!="fargate")] as $ec2|($ec2|length) as $t|([$ec2[]|select((.metadata.labels["eks.amazonaws.com/compute-type"]//"")=="auto")]|length) as $auto| if (($cl.cluster.computeConfig.enabled==true) and $t>0 and $auto==$t) then "all~every EC2 node is an EKS Auto Mode node (eks.amazonaws.com/compute-type=auto) and Auto Mode runs CoreDNS as a system service on each node, caching DNS queries on the node itself" elif ([.items[]?]|length)==0 then "na~no DaemonSets possible (serverless compute)" elif ([.items[]|select(.metadata.name|test("nodelocaldns|node-local-dns"))]|length)>0 then "all~nodelocal dns" elif ($cl.cluster.computeConfig.enabled==true) then "none~Auto Mode compute is enabled but \($auto) of \($t) EC2 nodes carry eks.amazonaws.com/compute-type=auto; the rest resolve through the CoreDNS Deployment, which they must keep, and no nodelocaldns DaemonSet caches for them" else "none~none" end'
# lens-3 ANSWERS `all` on the same all-nodes-auto gate, and the reason is the sentence above: on Auto Mode
# there is no CoreDNS Deployment to autoscale (auto-networking.html -- "EKS Auto Mode does not use the
# traditional CoreDNS deployment ... Auto Mode nodes utilize CoreDNS running as a system service directly
# on each node"), so DNS capacity tracks the node count, and the node count is what Auto Mode itself
# autoscales: docs.aws.amazon.com/eks/latest/userguide/automode.html -- "Auto scaling: Relying on Karpenter
# auto scaling, EKS Auto Mode monitors for unschedulable Pods and makes it possible for new nodes to be
# deployed to run those Pods."
# lens-2 already answers `all` on this exact cluster fact. Leaving lens-3 at `none` had the two questions
# contradicting each other about one mechanism -- "DNS runs on every node" and "DNS cannot scale" in the
# same report -- which is the two-verdicts-one-fact failure rel-16's comment describes. Its remediation
# (deploy a CoreDNS autoscaler) is inapplicable here and the prose below says so.
# Same gate as lens-2, deliberately: a hybrid cluster keeps a real CoreDNS Deployment, so it falls through
# to measuring the autoscaler and the final arm says which nodes still depend on it.
m3 lens-3 deployments nodes cluster 'input as $n|input as $cl|[$n.items[]?|select((.metadata.labels["eks.amazonaws.com/compute-type"]//"")!="fargate")] as $ec2|($ec2|length) as $t|([$ec2[]|select((.metadata.labels["eks.amazonaws.com/compute-type"]//"")=="auto")]|length) as $auto| if (($cl.cluster.computeConfig.enabled==true) and $t>0 and $auto==$t) then "all~there is no CoreDNS Deployment to autoscale: Auto Mode runs CoreDNS as a node system service, so DNS capacity follows the node count, which Auto Mode scales itself" elif ([.items[]|select(.metadata.name|test("dns-autoscaler|proportional-autoscaler"))]|length)>0 then "all~coredns autoscaler" elif ($cl.cluster.computeConfig.enabled==true) then "none~Auto Mode compute is enabled but \($auto) of \($t) EC2 nodes are Auto Mode nodes, so the CoreDNS Deployment the others depend on is still load-bearing and has no autoscaler" else "none~none" end'
m2 lens-14 nat nodes 'input as $n|([.NatGateways[]?|select(.State=="available")]|length) as $nat|([$n.items[]|.metadata.labels["topology.kubernetes.io/zone"]//empty]|unique|length) as $az| if $az==0 then "na~no nodes" elif $nat>=$az then "all~\($nat) NAT/\($az) AZ" elif $nat>0 then "some~\($nat) NAT/\($az) AZ" else "none~0 NAT" end'
# lens-15 — a subnet is PRIVATE when its route table has no route to an internet gateway. AWS:
# "You can explicitly associate a subnet with a particular route table. Otherwise, the subnet is
# implicitly associated with the main route table." So the algorithm needs the MAIN-TABLE FALLBACK:
# an implicitly-associated subnet returns an EMPTY per-subnet association list, and a naive lookup
# therefore finds nothing and silently mis-scores it.
# This previously tested MapPublicIpOnLaunch, which is auto-assign-public-IP — a proxy, not the
# definition. A subnet can have it false and still route 0.0.0.0/0 to an IGW, so the proxy false-PASSES
# on a weight-3 question. An earlier route-table attempt was abandoned because it "disagreed 3/3";
# that disagreement was the missing main-table fallback, not evidence against the correct rule.
# A subnet whose table cannot be resolved counts as NOT private: never claim private without evidence.
m3 lens-15 subnets cluster routetables 'input as $cl|input as $rt|(($cl.cluster.resourcesVpcConfig.subnetIds)//[]) as $own|[.Subnets[]?|select(($own|length)==0 or (.SubnetId as $id|$own|index($id)))] as $s|($s|length) as $t|([$rt.RouteTables[]?|select([.Associations[]?|select(.Main==true)]|length>0)]|first) as $main|([$s[]|.SubnetId as $sid|((([$rt.RouteTables[]?|select([.Associations[]?|select(.SubnetId==$sid)]|length>0)]|first)) // $main) as $tbl|select(($tbl!=null) and (([$tbl.Routes[]?|select((.GatewayId//"")|startswith("igw-"))]|length)==0))]|length) as $ok| if $t==0 then "na~no cluster subnets" else b($ok;$t)+"~\($ok)/\($t) private (no IGW route, cluster subnets)" end'
```

**Governance (interview in `interactive` mode):** rel-10/rel-12 (volume snapshot/backup policy), rel-14
(HA ingress controller), rel-15 (LoadBalancer usage), rel-17 (CoreDNS/External DNS strategy).

---

## Stop guessing capacity

### rel-1: Are worker nodes deployed across multiple Availability Zones?

**Detection:** 🔬 AUTO-DETECTABLE

> Multi-AZ deployment ensures the cluster survives an AZ failure.

**Commands:**
```bash
kubectl get nodes -o json
# Check topology.kubernetes.io/zone labels for 3+ unique zones
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`

**Remediation:** Deploy worker nodes across 3+ AZs: update node group subnets to span multiple availability zones. Use `eksctl create nodegroup --subnet-ids <az1>,<az2>,<az3>`.

---

### rel-2: Are PodDisruptionBudgets configured for critical deployments?

**Detection:** 🔬 AUTO-DETECTABLE

> PDBs prevent all replicas from being evicted simultaneously during node maintenance.

**Commands:**
```bash
kubectl get pdb -A -o json
kubectl get deployments -A -o json
# Compare PDB count vs deployment count
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`

**Remediation:** `--min-available` must be set **strictly below** the Deployment's current replica
count. On a single-replica Deployment, `--min-available=1` requires that one pod never be evicted —
`kubectl drain`, managed node group upgrades and Karpenter consolidation all block indefinitely waiting
for a voluntary disruption the PDB will never allow. Check the replica count, create the PDB below it,
then confirm the result is actually satisfiable:

```bash
kubectl get deployment <name> -n <ns> -o jsonpath='{.spec.replicas}'
kubectl create pdb <name> --selector=app=<label> --min-available=<replicas - 1> -n <ns>
kubectl get pdb <name> -n <ns> -o jsonpath='{.status.disruptionsAllowed}'   # must be >=1
```

If replicas is 1, fix that first — see `rel-7`. A PDB cannot make a single replica safe to evict.

---

### rel-3: Do containers have CPU and memory limits set?

**Detection:** 🔬 AUTO-DETECTABLE

> Resource limits prevent a single container from consuming all node resources.

**Commands:**
```bash
kubectl get pods -A -o json
# Check spec.containers[].resources.limits for cpu and memory
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`

**Remediation:** Set CPU and memory limits on all containers: `resources: { limits: { cpu: "500m", memory: "512Mi" } }`. Use VPA recommendations as a starting point.

---

### rel-4: Is a cluster autoscaler (Cluster Autoscaler or Karpenter) deployed?

**Detection:** 🔬 AUTO-DETECTABLE

> Autoscalers add nodes when pods are pending and remove underutilized nodes.
> **EKS Auto Mode satisfies this question with no autoscaler workload in the cluster**, and the verdict
> is read from `computeConfig.enabled`, not from a Deployment. AWS: "Auto scaling: Relying on Karpenter
> auto scaling, EKS Auto Mode monitors for unschedulable Pods and makes it possible for new nodes to be
> deployed to run those Pods. As workloads are terminated, EKS Auto Mode dynamically disrupts and
> terminates nodes when they are no longer needed, optimizing resource usage." Do not read an `all` on
> such a cluster as "a controller was found" — nothing runs in the cluster to find. AWS also applies
> `karpenter.sh/nodepool` to every node it provisions, so a label-based search **appears** to find OSS
> Karpenter on an Auto Mode cluster; the cluster field is the answer, the label is a coincidence.

**Commands:**
```bash
kubectl get pods -n karpenter -o json 2>/dev/null
kubectl get deployments -A -o json
# Look for karpenter or cluster-autoscaler
aws eks describe-cluster --name <CLUSTER> --region <REGION> --query "cluster.computeConfig.enabled"
# true -> autoscaling is a service capability; an empty result from the two commands above is expected
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`

**Remediation:** Deploy Karpenter or Cluster Autoscaler: `helm install karpenter oci://public.ecr.aws/karpenter/karpenter`. Configure NodePools for automatic scaling.

**On an Auto Mode cluster, do not install either** — AWS suggests "running either EKS Auto Mode or
self-managed Karpenter", and if both are present the node pools have to be partitioned so each workload
belongs to exactly one of them. What is worth checking there instead is that your NodePool limits and
disruption settings are not blocking consolidation, and that PDBs (`rel-2`) do not stall the 21-day node
replacement Auto Mode enforces.

---

### rel-5: Are Horizontal Pod Autoscalers configured for deployments?

**Detection:** 🔬 AUTO-DETECTABLE

> HPAs scale pod replicas based on CPU/memory or custom metrics.

**Commands:**
```bash
kubectl get hpa -A -o json
kubectl get deployments -A -o json
# Count HPAs vs deployments
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`

**Remediation:** Add HPAs to stateless deployments: `kubectl autoscale deployment <name> --cpu-percent=70 --min=2 --max=10`.

---

### rel-6: Do containers have readiness probes configured?

**Detection:** 🔬 AUTO-DETECTABLE

> Readiness probes prevent traffic from being sent to pods that are not ready.

**Commands:**
```bash
kubectl get pods -A -o json
# Check spec.containers[].readinessProbe is defined
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`

**Remediation:** Add readiness probes to all containers: `readinessProbe: { httpGet: { path: /healthz, port: 8080 }, initialDelaySeconds: 5, periodSeconds: 10 }`.

---

## Self-Healing Architecture

### rel-7: Do deployments run with more than one replica?

**Detection:** 🔬 AUTO-DETECTABLE

> Multiple replicas ensure availability during pod failures or rolling updates.

**Commands:**
```bash
kubectl get deployments -A -o json
# Check spec.replicas > 1
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`

**Remediation:** Set `spec.replicas: 2` or higher for all production deployments. Single-replica deployments have zero availability during pod restarts.

---

### rel-8: Are pod anti-affinity rules configured to spread replicas across nodes?

**Detection:** 🔬 AUTO-DETECTABLE

> Anti-affinity prevents all replicas from landing on the same node.

**Commands:**
```bash
kubectl get deployments -A -o json
# Check spec.template.spec.affinity.podAntiAffinity
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`

**Remediation:** Add pod anti-affinity rules: `affinity.podAntiAffinity.preferredDuringSchedulingIgnoredDuringExecution` with `topologyKey: kubernetes.io/hostname`.

---

### rel-9: Are topology spread constraints configured to distribute pods across zones?

**Detection:** 🔬 AUTO-DETECTABLE

> Topology spread ensures pods are distributed across AZs for zone-level resilience.

**Commands:**
```bash
kubectl get deployments -A -o json
# Check spec.template.spec.topologySpreadConstraints
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`

**Remediation:** Add topology spread constraints: `topologySpreadConstraints: [{ maxSkew: 1, topologyKey: topology.kubernetes.io/zone, whenUnsatisfiable: ScheduleAnyway }]`.

---

### rel-10: Are VolumeSnapshot classes and snapshots configured for persistent volume backup?

**Detection:** ✋ ASK USER

> Volume snapshots enable point-in-time recovery for stateful workloads.

**Ask the user this question.** Interpret their response:
- "Yes, fully" / "We do this everywhere" → `all`
- "Mostly" / "For most workloads" → `most`
- "Partially" / "Working on it" → `some`
- "No" / "Not yet" → `none`
- "Doesn't apply" → `na`

**Remediation:** Install the EBS CSI Driver snapshot controller and create a VolumeSnapshotClass to enable automated PV backups.

---

### rel-11: Are PersistentVolumeClaims in a Bound state?

**Detection:** 🔬 AUTO-DETECTABLE

> Unbound PVCs indicate storage provisioning failures that could affect workloads.

**Remediation:** Investigate unbound PVCs. Note that `--field-selector status.phase!=Bound` does
**not** work on PersistentVolumeClaims — Kubernetes registers only `metadata.name` and
`metadata.namespace` as selectable fields for PVCs, so that form fails with
`field label not supported: status.phase`. Filter client-side instead:

```bash
kubectl get pvc -A -o json \
  | jq -r '.items[]|select(.status.phase!="Bound")
           |"\(.metadata.namespace)/\(.metadata.name)\t\(.status.phase)\t\(.spec.storageClassName//"-")"'
```

Then for each, check that the StorageClass provisioner exists, that its zone matches where the pod
is scheduled (a `WaitForFirstConsumer` class binds only once a pod is placed), and that the
requested capacity is available.

---

### rel-12: Are VolumeSnapshot policies configured for automated backup?

**Detection:** ✋ ASK USER

> Automated snapshot policies ensure regular backups without manual intervention.

**Ask the user this question.** Interpret their response:
- "Yes, fully" / "We do this everywhere" → `all`
- "Mostly" / "For most workloads" → `most`
- "Partially" / "Working on it" → `some`
- "No" / "Not yet" → `none`
- "Doesn't apply" → `na`

**Remediation:** A high Reliability score is not evidence a backup exists — nor is a snapshot that
has never been restored a tested backup. Prerequisites, in order:

1. **EBS CSI driver with snapshot support** — the `csi-snapshotter` sidecar must be running on the
   controller: `kubectl get pods -n kube-system -l app=ebs-csi-controller -o jsonpath='{.items[*].spec.containers[*].name}'`.
2. **The external-snapshotter CRDs and controller** — `VolumeSnapshotClass`, `VolumeSnapshotContent`,
   `VolumeSnapshot` (`kubectl get crd | grep snapshot.storage.k8s.io`); without the controller reconciling
   them, a `VolumeSnapshot` object is created and never becomes `readyToUse`.
3. **A `VolumeSnapshotClass`** naming the driver:

```yaml
apiVersion: snapshot.storage.k8s.io/v1
kind: VolumeSnapshotClass
metadata:
  name: ebs-snapshot-class
driver: ebs.csi.aws.com
deletionPolicy: Delete
```

4. **A schedule** — either a CronJob that creates a `VolumeSnapshot` referencing the target PVC on a
   recurring basis, or a managed path that replaces steps 3-4 outright: **AWS Backup** (native EBS/EFS
   backup plans with retention and cross-region copy) or **Velero with the AWS plugin** (namespace-aware —
   restores the Kubernetes objects, not just the volume). Either is less to operate than hand-rolled
   CronJob YAML.

**Verify a snapshot actually completes, then verify it actually restores** — a CronJob existing proves
neither:

```bash
kubectl get volumesnapshot -n <ns> <name> -o jsonpath='{.status.readyToUse}'   # must be true
# Then, on a schedule you repeat, prove restore works — a throwaway PVC/pod from the snapshot,
# not just a green snapshot job.
```

A snapshot that has never been restored is not a tested backup.

---

## Failure Management

### rel-13: Are monitoring tools (Prometheus, CloudWatch, Datadog) deployed for alerting?

**Detection:** 🔬 AUTO-DETECTABLE

> Monitoring and alerting enable proactive detection of reliability issues.

**Commands:**
```bash
kubectl get deployments -A -o json
# Look for prometheus, grafana, datadog, cloudwatch
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`

**Remediation:** Deploy Prometheus + Grafana for monitoring: `helm install prometheus prometheus-community/kube-prometheus-stack`. Configure alerting rules for critical metrics.

---

### rel-14: Are ingress controllers deployed with multiple replicas for high availability?

**Detection:** ✋ ASK USER

> HA ingress controllers prevent a single point of failure for inbound traffic.

**Ask the user this question.** Interpret their response:
- "Yes, fully" / "We do this everywhere" → `all`
- "Mostly" / "For most workloads" → `most`
- "Partially" / "Working on it" → `some`
- "No" / "Not yet" → `none`
- "Doesn't apply" → `na`

**Remediation:** Scale ingress controllers to 2+ replicas: `kubectl scale deployment <ingress-controller> --replicas=3`. Add PDB with minAvailable=1.

---

### rel-15: Are LoadBalancer services used for external traffic exposure?

**Detection:** ✋ ASK USER

> LoadBalancer services distribute traffic across healthy pods.

**Ask the user this question.** Interpret their response:
- "Yes, fully" / "We do this everywhere" → `all`
- "Mostly" / "For most workloads" → `most`
- "Partially" / "Working on it" → `some`
- "No" / "Not yet" → `none`
- "Doesn't apply" → `na`

**Remediation:** Use Service type LoadBalancer for external traffic. Deploy AWS Load Balancer Controller for ALB/NLB integration.

---

### rel-16: Is a service mesh deployed for traffic management and circuit breaking?

**Detection:** 🔬 AUTO-DETECTABLE

> Service meshes provide retry logic, circuit breaking, and traffic shifting.

**Remediation:** Deploy Istio, Linkerd or Consul Connect for traffic management with circuit breaking, retries, and traffic shifting capabilities.

**This question and Security's `sec-27` can disagree about the same cluster** — no longer about Consul,
which both now credit. `rel-16` credits a Deployment named `istiod`,
`linkerd-destination`/`linkerd-controller` or `consul-connect`. `sec-27` (in
`security/identity-access.md`) credits `istiod`/`linkerd`/`consul-connect` by name **or** any Deployment
sitting in a namespace matching `istio-system`/`linkerd`/`consul`. Every Deployment `rel-16` matches,
`sec-27` matches too, so the divergence now runs one way only — `sec-27` "mesh present" against `rel-16`
"no mesh" — and it means one of two things. Either the mesh is real but not conventionally named (a
Consul control plane in namespace `consul` with no `consul-connect` Deployment, or `linkerd-viz` with no
`linkerd-destination`), and `sec-27` is the one to believe; or some Deployment merely sits in a namespace
*named* for a mesh that has no control plane in it — an app namespace called `consul`, an `istio-system`
left over from an uninstall — and `rel-16` is right. `sec-28` (mTLS enforced) reads Istio/Linkerd
sidecars and Istio `PeerAuthentication` only; when pods carry Consul's
`envoy-sidecar`/`consul-dataplane` it returns `na` with that reason, so a Consul mesh's mTLS posture is
reported NOT ASSESSED rather than absent. Nothing in the report reconciles the questions; read them
together.

---

### rel-17: Are CoreDNS and External DNS configured for service discovery?

**Detection:** ✋ ASK USER

> Reliable DNS is critical for service-to-service communication.

**Ask the user this question.** Interpret their response:
- "Yes, fully" / "We do this everywhere" → `all`
- "Mostly" / "For most workloads" → `most`
- "Partially" / "Working on it" → `some`
- "No" / "Not yet" → `none`
- "Doesn't apply" → `na`

**Remediation:** Verify CoreDNS is running: `kubectl get pods -n kube-system -l k8s-app=kube-dns`. Deploy External DNS for automatic Route53 management.

---

### rel-18: Do deployments use RollingUpdate strategy?

**Detection:** 🔬 AUTO-DETECTABLE

> Rolling updates ensure zero-downtime deployments by gradually replacing pods.

**Commands:**
```bash
kubectl get deployments -A -o json
# Check spec.strategy.type == "RollingUpdate"
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`

**Remediation:** Set `strategy.type: RollingUpdate` with `maxUnavailable: 25%` and `maxSurge: 25%` on all Deployments for zero-downtime updates.

---

### rel-19: Do DaemonSets use RollingUpdate strategy?

**Detection:** 🔬 AUTO-DETECTABLE

> Rolling updates for DaemonSets prevent all node agents from restarting simultaneously.

**Remediation:** Set `updateStrategy.type: RollingUpdate` on DaemonSets with `maxUnavailable: 1` to prevent all node agents from restarting simultaneously.

---

## Disaster Recovery

### rel-20: Do DaemonSet containers have resource requests and limits set?

**Detection:** 🔬 AUTO-DETECTABLE

> Resource constraints on DaemonSets prevent them from starving workload pods.

**Remediation:** Add resource requests and limits to all DaemonSet containers to prevent them from starving workload pods on the same node.

---

## Resilience Testing

### rel-21: Do StatefulSets use persistent storage (volumeClaimTemplates or PVCs)?

**Detection:** 🔬 AUTO-DETECTABLE

> Persistent storage ensures StatefulSet data survives pod restarts.

**Remediation:** Use `volumeClaimTemplates` in StatefulSet specs for persistent storage. This ensures each replica gets its own dedicated PVC.

---

## Dependency Management

### rel-22: Do StatefulSets run more than one replica?

**Detection:** 🔬 AUTO-DETECTABLE — the scorer checks `.spec.replicas > 1` on each StatefulSet.
**It does NOT check PodDisruptionBudgets**, despite what earlier revisions of this section claimed:
PDB coverage is measured separately by `rel-2`, which matches PDB selectors against workload labels.
Do not report an `all` here as evidence that StatefulSets are PDB-protected — that is a different
question with a different answer.

> A single-replica StatefulSet has no availability during a node drain, an AZ event, or its own
> rolling update: the one pod terminates before its replacement can attach the volume. Note that
> `replicas > 1` alone is not sufficient for a quorum-based system — a 2-replica etcd or ZooKeeper
> cannot form a majority — so read this as "not obviously single-pointed", not as "HA".

**Remediation:** Scale to the replica count the workload's own consensus model requires (3 for
quorum systems, 2+ for active/passive), and verify the volume claim template provisions per-replica
storage rather than sharing one volume:

```bash
kubectl scale statefulset/<name> -n <ns> --replicas=3
kubectl get statefulset <name> -n <ns> -o jsonpath='{.spec.volumeClaimTemplates[*].metadata.name}'
```

Then confirm a PDB actually selects those pods — see `rel-2`.

---

## Observability

### rel-23: Do you implement distributed tracing (AWS X-Ray, Jaeger, Zipkin) for request flow visibility?

**Detection:** 🔬 AUTO-DETECTABLE

> Distributed tracing enables root cause analysis across microservices.

**Remediation:** Deploy distributed tracing: `helm install jaeger jaegertracing/jaeger`. Or enable AWS X-Ray with the ADOT collector for request flow visibility.

---

## EKS Best Practices

> Questions prefixed `lens-` come from the **EKS Best Practices Guides**
> (aws.github.io/aws-eks-best-practices) and the EKS User Guide, not from the AWS
> Well-Architected Framework's own question set. They are scored the same way and reported
> alongside the Framework questions because they measure the same properties on EKS
> specifically; the prefix is what distinguishes their source.

### lens-2: Is NodeLocal DNSCache deployed for DNS performance?

**Detection:** 🔬 AUTO-DETECTABLE

> NodeLocal DNSCache reduces DNS latency and CoreDNS load.
> **EKS Auto Mode already caches DNS on the node — but only on nodes that are Auto Mode nodes.** AWS:
> "EKS Auto Mode does not use the traditional CoreDNS deployment to provide DNS resolution within the
> cluster. Instead, Auto Mode nodes utilize CoreDNS running as a system service directly on each node."
> On a **hybrid** cluster that credit does not transfer: "If you plan to maintain a cluster with both
> Auto Mode and non-Auto Mode nodes, you must retain the CoreDNS deployment. Non-Auto Mode nodes rely on
> the traditional CoreDNS pods for DNS resolution, as they cannot access the node-level DNS service that
> Auto Mode provides." So this question scores `all` only when **every** EC2 node carries
> `eks.amazonaws.com/compute-type: auto` — the label AWS documents as identifying Auto Mode managed
> nodes. Otherwise it measures the `nodelocaldns` DaemonSet as it always has.

**Commands:**
```bash
kubectl get daemonsets -A -o json
# Look for nodelocaldns or node-local-dns
kubectl get nodes -L eks.amazonaws.com/compute-type
# Every EC2 node "auto" -> node-level DNS everywhere. A mix -> the CoreDNS Deployment is still serving
# the non-Auto-Mode nodes, and a cache for them has to be deployed or done without.
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`
- every EC2 node labelled `compute-type: auto` on an Auto Mode cluster → `all` (Fargate nodes excluded from that test, and a cluster with no EC2 node never satisfies it)

**Remediation:** Deploy NodeLocal DNSCache to reduce DNS latency: follow the EKS documentation for nodelocaldns DaemonSet deployment.

**On a hybrid cluster, deploy it for the non-Auto-Mode nodes only** (a `nodeAffinity` with
`eks.amazonaws.com/compute-type NotIn [auto]` keeps it off the Auto Mode nodes, which do not need it and
where a DaemonSet cannot replace the node's own DNS service). On an all-Auto-Mode cluster there is
nothing to deploy.

---

### lens-3: Is a CoreDNS autoscaler deployed?

**Detection:** 🔬 AUTO-DETECTABLE

> CoreDNS autoscaler prevents DNS bottlenecks as the cluster grows.
> **On an all-Auto-Mode cluster there is no CoreDNS Deployment to autoscale**, so this scores `all` on
> the same gate as `lens-2`: AWS runs CoreDNS "as a system service directly on each node", which puts DNS
> capacity in step with the node count, and the node count is the thing Auto Mode autoscales — "EKS Auto
> Mode monitors for unschedulable Pods and makes it possible for new nodes to be deployed to run those
> Pods." Scoring this `none` while `lens-2` scores `all` would have the report contradict itself about one
> cluster fact. On a **hybrid** cluster the CoreDNS Deployment is retained and load-bearing for the
> non-Auto-Mode nodes, so the question measures the autoscaler as before.

**Commands:**
```bash
kubectl get deployments -A -o json
# Look for dns-autoscaler or proportional-autoscaler
kubectl get deployment coredns -n kube-system
# On an all-Auto-Mode cluster this returns NotFound, which is the expected shape, not a finding.
kubectl get nodes -L eks.amazonaws.com/compute-type
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`
- every EC2 node labelled `compute-type: auto` on an Auto Mode cluster → `all` (same gate as `lens-2`)

**Remediation:** Deploy a CoreDNS autoscaler (dns-autoscaler or proportional-autoscaler) to scale CoreDNS replicas based on cluster size.

**This remediation does not apply to an all-Auto-Mode cluster** — there is no CoreDNS Deployment there to
give an autoscaler a scale target, and deploying one would be a no-op at best. On a hybrid cluster it does
apply, and it applies to the CoreDNS Deployment that AWS says you must retain for the non-Auto-Mode nodes;
size it against those nodes, not against the whole fleet.

---

### lens-14: Are NAT Gateways deployed per-AZ for redundancy?

**Detection:** 🔬 AUTO-DETECTABLE

> Per-AZ NAT Gateways prevent single-AZ failures from breaking outbound traffic.

**Commands:**
```bash
aws ec2 describe-nat-gateways --filter Name=vpc-id,Values=<VPC_ID> --region <REGION>
# Check NAT GWs exist in each AZ used by the cluster
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`

**Remediation:** Deploy NAT Gateways in each AZ used by the cluster. Create one NAT Gateway per public subnet across all AZs for redundancy.

---

### lens-15: Are worker nodes deployed in private subnets?

**Detection:** 🔬 AUTO-DETECTABLE

> Private subnets prevent direct internet access to worker nodes.

**Commands:**
```bash
aws ec2 describe-route-tables --filters Name=vpc-id,Values=<VPC_ID> --region <REGION>
# A subnet is PRIVATE when its route table has NO route whose GatewayId starts with "igw-".
# Use the subnet's explicitly-associated table; fall back to the VPC's main table if it has none.
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`

**Remediation:** Remove the internet gateway route from the route tables serving the node subnets, and
route `0.0.0.0/0` to a NAT gateway in a public subnet instead.

> **Read this before running anything.** You are editing the default route of a live subnet. `replace-route`
> is used rather than delete-then-create because a failed `create-route` after a successful `delete-route`
> leaves the subnet with **no default route at all** — every node in it loses outbound connectivity,
> including image pulls and the kubelet's path to the control plane. Confirm the NAT gateway exists and is
> `available` in a *different* (public) subnet first, and do one route table at a time.

```bash
# 1. confirm the NAT gateway is usable before touching any route
aws ec2 describe-nat-gateways --nat-gateway-ids <NAT_ID> --region <REGION> \
  --query 'NatGateways[].{State:State,Subnet:SubnetId}'

# 2. atomically repoint the default route — no window with the subnet unrouted
aws ec2 replace-route --route-table-id <RTB_ID> --destination-cidr-block 0.0.0.0/0 \
  --nat-gateway-id <NAT_ID> --region <REGION>
```

Existing nodes keep their public IPs until replaced, so cycle the node group afterwards. Note that
setting `MapPublicIpOnLaunch=false` alone will **not** satisfy this check: it stops new instances
getting a public IP, but a subnet whose route table still reaches an internet gateway is still a public
subnet, and nodes already running in it keep the addresses they were given.

---
