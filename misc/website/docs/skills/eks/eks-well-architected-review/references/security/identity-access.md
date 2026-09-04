---
title: "🔒 Security — Identity & Access Management"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-well-architected-review/references/security/identity-access.md
format: md
---

:::info[Source]
This page is generated from [skills/eks-well-architected-review/references/security/identity-access.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-well-architected-review/references/security/identity-access.md). Edit the source, not this page.
:::

# 🔒 Security — Identity & Access Management

**13 questions** — API endpoint access, IAM role mapping, IRSA, OIDC, aws-auth, ClusterRole least privilege, RBAC bindings.

Scoring is **deterministic** — each measured question is answered by the `jq` in the scorer block below,
which prints `all`/`most`/`some`/`none`/`na` (thresholds: ≥90 `all`, ≥70 `most`, >0 `some`, 0 `none`;
empty/not-applicable `na`). You run the command; you do not judge the JSON. Governance questions are
process-only and are not scored from cluster data.

> **The per-question `Detection:` tags below are explanatory only; the scorer block decides
> measured vs governance.** Where a section says `✋ ASK USER` for a question the scorer emits as
> `measured`, the SCORER IS AUTHORITATIVE — answer it from the collected data and ignore the
> "Ask the user this question" block. Use the prose for rationale and remediation wording only.
> (This file holds the scorer for the ENTIRE Security pillar, including the questions documented in
> data-protection.md, network.md, workload-security.md and governance-compliance.md.)

---

## Security pillar scorer — run verbatim (covers all 54 Security questions)

This single block scores the **entire Security pillar** (this file + data-protection, network,
workload-security, governance-compliance). It requires `$WORK` (set in SKILL.md Step 2) populated with the
canonical JSON files, and appends one JSONL line per question to `$WORK/results.jsonl`.

- **auto mode:** run as-is. Governance questions emit `state:"unknown"` (reported as Not Assessed).
- **interactive mode:** after collecting the user's answers, replace each governance `g <id>` call with
  `emit <id> governance <all|most|some|none|na> "<note>"`.

```bash
W="$WORK"
B='def b($ok;$t): if $t==0 then "na" elif ($ok*100/$t)>=90 then "all" elif ($ok*100/$t)>=70 then "most" elif $ok>0 then "some" else "none" end;'
emit(){ printf '{"pillar":"security","id":"%s","track":"%s","state":"%s","detail":"%s"}\n' "$1" "$2" "$3" "$4" >> "$W/results.jsonl"; }
g(){ emit "$1" governance unknown ""; }
m(){ local id="$1" f="$2" p="$3" r st d; r=$(jq -r "$B $p" "$W/$f.json" 2>&1) || { printf 'SCORER ABORT [%s]: jq failed — a missing or malformed collection file is NOT a finding, and must never be scored as one. jq said: %s\n' "$id" "$r" >&2; exit 1; }; [ -n "$r" ] || { printf 'SCORER ABORT [%s]: jq produced no output\n' "$id" >&2; exit 1; }; st="${r%%~*}"; d="${r#*~}"; [ "$r" = "$st" ]&&d=""; emit "$id" measured "${st:-none}" "$d"; }
m2(){ local id="$1" f1="$2" f2="$3" p="$4" r st d; r=$(jq -r "$B $p" "$W/$f1.json" "$W/$f2.json" 2>&1) || { printf 'SCORER ABORT [%s]: jq failed — a missing or malformed collection file is NOT a finding, and must never be scored as one. jq said: %s\n' "$id" "$r" >&2; exit 1; }; [ -n "$r" ] || { printf 'SCORER ABORT [%s]: jq produced no output\n' "$id" >&2; exit 1; }; st="${r%%~*}"; d="${r#*~}"; [ "$r" = "$st" ]&&d=""; emit "$id" measured "${st:-none}" "$d"; }
# Three inputs, for checks whose applicability depends on the compute MODE, not just its state.
# In jq, `input` yields f2 then f3 in order.
m3(){ local id="$1" f1="$2" f2="$3" f3="$4" p="$5" r st d; r=$(jq -r "$B $p" "$W/$f1.json" "$W/$f2.json" "$W/$f3.json" 2>&1) || { printf 'SCORER ABORT [%s]: jq failed — a missing or malformed collection file is NOT a finding, and must never be scored as one. jq said: %s\n' "$id" "$r" >&2; exit 1; }; [ -n "$r" ] || { printf 'SCORER ABORT [%s]: jq produced no output\n' "$id" >&2; exit 1; }; st="${r%%~*}"; d="${r#*~}"; [ "$r" = "$st" ]&&d=""; emit "$id" measured "${st:-none}" "$d"; }
# Four inputs, for `sec-6`: workload identity can be delivered by EITHER Pod Identity OR IRSA, and
# IRSA is only real if the IAM OIDC provider is registered — that is 4 separate collection files.
m4(){ local id="$1" f1="$2" f2="$3" f3="$4" f4="$5" p="$6" r st d; r=$(jq -r "$B $p" "$W/$f1.json" "$W/$f2.json" "$W/$f3.json" "$W/$f4.json" 2>&1) || { printf 'SCORER ABORT [%s]: jq failed — a missing or malformed collection file is NOT a finding, and must never be scored as one. jq said: %s\n' "$id" "$r" >&2; exit 1; }; [ -n "$r" ] || { printf 'SCORER ABORT [%s]: jq produced no output\n' "$id" >&2; exit 1; }; st="${r%%~*}"; d="${r#*~}"; [ "$r" = "$st" ]&&d=""; emit "$id" measured "${st:-none}" "$d"; }

# ── identity-access (13) ──
m sec-1 cluster 'if .cluster.resourcesVpcConfig.endpointPrivateAccess==true then "all~private endpoint on" else "none~private endpoint off" end'
m sec-2 cluster '.cluster.resourcesVpcConfig as $v| if $v.endpointPublicAccess==false then "all~public disabled" elif (($v.publicAccessCidrs//[])|any(.=="0.0.0.0/0")) then "none~public 0.0.0.0/0" elif (($v.publicAccessCidrs//[])|length)>0 then "all~public restricted" else "none~public open" end'
g sec-3
g sec-5
# sec-6 — workload identity. Counts BOTH mechanisms: EKS Pod Identity (which AWS now recommends over
# IRSA) and IRSA. Pod Identity uses NO ServiceAccount annotation — associations exist only in the EKS
# API — so a scorer that reads only `eks.amazonaws.com/role-arn` reports a correctly-built Pod
# Identity cluster as having no workload identity at all. IRSA additionally requires the IAM OIDC
# provider to be REGISTERED: the annotation alone is inert without it (see sec-18).
m4 sec-6 serviceaccounts cluster oidcproviders podidentity 'input as $cl|input as $op|input as $pi|(($cl.cluster.identity.oidc.issuer // "")|sub("^https://";"")) as $iss|((($iss|length)>0) and ([$op.OpenIDConnectProviderList[]?.Arn // empty]|any(endswith("oidc-provider/"+$iss)))) as $oidcok|([.items[]?|select(.metadata.annotations["eks.amazonaws.com/role-arn"])]|length) as $irsa|([$pi.associations[]?]|length) as $pia| if $pia>0 and ($oidcok and $irsa>0) then "all~\($pia) Pod Identity assoc + \($irsa) IRSA SAs" elif $pia>0 then "all~\($pia) Pod Identity association(s)" elif ($oidcok and $irsa>0) then "all~\($irsa) IRSA SAs" elif $irsa>0 then "none~\($irsa) IRSA annotation(s) but no IAM OIDC provider registered — inert" else "none~no workload identity (no Pod Identity associations, no IRSA)" end'
g sec-7
m sec-9 clusterroles '[.items[]|select(.metadata.name|test("^system:|^eks:|^cluster-admin$")|not)] as $r|($r|length) as $t|([$r[]|select([.rules[]?|select((.resources[]?=="*") or (.verbs[]?=="*"))]|length==0)]|length) as $ok| b($ok;$t)+"~\($ok)/\($t) no-wildcard (custom roles)"'
m sec-17 cluster '(.cluster.accessConfig.authenticationMode // "CONFIG_MAP") as $mm| if ($mm=="API" or $mm=="API_AND_CONFIG_MAP") then "all~"+$mm else "some~"+$mm end'
# sec-18 — the IAM OIDC identity provider must actually EXIST. `cluster.identity.oidc.issuer` is
# populated on every EKS cluster ever created; it is the *input* to `aws iam
# create-open-id-connect-provider`, not evidence the provider was created. Scoring off the issuer
# alone was a High-severity pass that could not fail on any real cluster. Match the issuer (scheme
# stripped) against the provider ARN suffix so a provider belonging to a DIFFERENT cluster in the
# same account does not count — the same scoping rule the EBS/subnet/SG queries follow.
# `na` when the cluster has no IRSA ServiceAccounts: there is then no IRSA to enable, so demanding a
# provider would fire a false High finding at a correctly-built Pod-Identity-only cluster, and would
# double-count the gap sec-6 already reports. `none` is reserved for the trap this question exists to
# catch — IRSA annotations that grant nothing because no matching provider is registered.
m3 sec-18 cluster oidcproviders serviceaccounts 'input as $p|input as $sa|((.cluster.identity.oidc.issuer // "")|sub("^https://";"")) as $iss|[$p.OpenIDConnectProviderList[]?.Arn // empty] as $arns|([$sa.items[]?|select(.metadata.annotations["eks.amazonaws.com/role-arn"])]|length) as $irsa| if $irsa==0 then "na~no IRSA ServiceAccounts, so no IAM OIDC provider is required (workload identity is scored by sec-6)" elif ($iss|length)==0 then "none~\($irsa) IRSA SA(s) but the cluster reports no OIDC issuer" elif ($arns|any(endswith("oidc-provider/"+$iss))) then "all~IAM OIDC provider registered for the cluster issuer (\($irsa) IRSA SAs)" else "none~\($irsa) IRSA SA(s) but NO IAM OIDC provider matches the cluster issuer (\($arns|length) in account) — the annotations grant nothing" end'
m rbac-1 clusterrolebindings '[.items[]|select(.roleRef.name=="cluster-admin")] as $bb|([$bb[]|.subjects[]?|select(((.name//"")|test("^system:|^eks:"))|not)|select(.name!="system:masters")]|length) as $ns| if ($bb|length)==0 then "na~none" elif $ns==0 then "all~system-only" else "none~\($ns) nonsystem" end'
m2 rbac-2 rolebindings clusterrolebindings 'input as $crb|[.items[]?|select(((.metadata.namespace//"")|test("^(kube-|amazon-)"))|not)|(.metadata.namespace//"") as $bns|.subjects[]?|select(.kind=="ServiceAccount")|(((.namespace//$bns)|if .=="" then $bns else . end)+"/"+.name)]|unique as $ns_bound|[$crb.items[]?|select(((.metadata.name//"")|test("^(system:|eks:)"))|not)|.subjects[]?|select(.kind=="ServiceAccount")|select(((.namespace//"")|test("^(kube-|amazon-)"))|not)|((.namespace//"")+"/"+.name)]|unique as $cluster_bound|(($ns_bound+$cluster_bound)|unique|length) as $t|(($ns_bound-$cluster_bound)|length) as $ok| if $t==0 then "na~no workload ServiceAccount bindings" else b($ok;$t)+"~\($ok)/\($t) SAs namespace-scoped only" end'
m2 rbac-3 rolebindings serviceaccounts 'input as $sa| ($sa.items|map(.metadata.namespace+"/"+.metadata.name)) as $known|[.items[]?|select(((.metadata.namespace//"")|test("^(kube-|amazon-)"))|not)|(.metadata.namespace//"") as $bns|.subjects[]?|select(.kind=="ServiceAccount")|(((.namespace//$bns)|if .=="" then $bns else . end)+"/"+.name)] as $refs|($refs|length) as $t|([$refs[]|select(. as $r|$known|index($r))]|length) as $ok| if $t==0 then "na~no workload SA bindings" else b($ok;$t)+"~\($ok)/\($t) resolve" end'
m rbac-4 serviceaccounts '[.items[]|select(.metadata.name=="default" and ((.metadata.namespace)|test("^kube-")|not))] as $d|($d|length) as $t|([$d[]|select(.automountServiceAccountToken==false)]|length) as $ok| b($ok;$t)+"~\($ok)/\($t) automount off"'

# ── data-protection (11) ──
m sec-8 deployments 'if ([.items[]|select(.metadata.name|test("external-secrets"))]|length)>0 then "all~ESO present" else "none~no ESO" end'
g sec-24
g sec-34
g sec-35
m2 sec-21 volumes cluster 'input as $cl|($cl.cluster.name//"") as $cn|[.Volumes[]?|select([.Tags[]?|select((.Key==("kubernetes.io/cluster/"+$cn)) or (.Value==$cn))]|length>0)] as $v|($v|length) as $t|([$v[]|select(.Encrypted==true)]|length) as $ok| if $t==0 then "na~no cluster-tagged volumes" else b($ok;$t)+"~\($ok)/\($t) encrypted (cluster vols)" end'
g sec-22
m sec-25 storageclasses '[.items[]|select((.provisioner//"")|test("ebs\\.csi\\.aws\\.com|kubernetes\\.io/aws-ebs"))] as $s|($s|length) as $t|([$s[]|select(.parameters.encrypted=="true")]|length) as $ok| if $t==0 then "na~no EBS StorageClass" else b($ok;$t)+"~\($ok)/\($t) encrypted EBS SC" end'
g sec-23
m sec-27 deployments 'if ([.items[]?|select(((.metadata.namespace//"")|test("istio-system|linkerd")) or (.metadata.name|test("istiod|linkerd")))]|length)>0 then "all~mesh present" else "none~no mesh" end'
m sec-28 pods '[.items[]|select((.metadata.namespace//"")|test("^(kube-|amazon-)")|not)] as $p|($p|length) as $t|([$p[]|select([.spec.containers[]?.name]|any(test("istio-proxy|linkerd-proxy")))]|length) as $ok| b($ok;$t)+"~\($ok)/\($t) sidecars (workloads)"'
m sec-29 ingresses '[.items[]] as $i|($i|length) as $t|([$i[]|select((.spec.tls//[])|length>0)]|length) as $ok| b($ok;$t)+"~\($ok)/\($t) TLS"'

# ── network (8) ──
m2 sec-4 namespaces networkpolicies 'input as $np|[.items[]|select(.metadata.name|test("^(kube-|amazon-)|^default$")|not)|.metadata.name] as $ns|($ns|length) as $t|($np.items|map(.metadata.namespace)|unique) as $cov|([$ns[]|select(. as $n|$cov|index($n))]|length) as $ok| b($ok;$t)+"~\($ok)/\($t) ns covered"'
g sec-14
m2 sec-30 sg cluster 'input as $cl|($cl.cluster.name//"") as $cn|($cl.cluster.resourcesVpcConfig) as $v|((($v.securityGroupIds//[]) + [$v.clusterSecurityGroupId//empty])|unique) as $own|[.SecurityGroups[]?|select((.GroupId as $id|$own|index($id)) or ([.Tags[]?|select((.Key==("kubernetes.io/cluster/"+$cn)) or (.Value==$cn))]|length>0))] as $g| if ($g|length)==0 then "na~no cluster SGs" elif ([$g[].IpPermissions[]?|select(((.FromPort//0)<=22 and (.ToPort//0)>=22) and (.IpRanges[]?.CidrIp=="0.0.0.0/0"))]|length)>0 then "none~ssh 0.0.0.0/0" else "all~no ssh open (cluster SGs)" end'
m sec-31 cluster '"na~same signal as net-4 (deduplicated)"'
m2 net-1 subnets cluster 'input as $cl|(($cl.cluster.resourcesVpcConfig.subnetIds)//[]) as $own|[.Subnets[]?|select(($own|length)==0 or (.SubnetId as $id|$own|index($id)))] as $s|($s|length) as $t|([$s[]|select(.AvailableIpAddressCount>=100)]|length) as $ok| if $t==0 then "na~no cluster subnets" else b($ok;$t)+"~\($ok)/\($t) >=100 IPs (cluster subnets)" end'
m2 net-2 sg cluster 'input as $cl|($cl.cluster.name//"") as $cn|($cl.cluster.resourcesVpcConfig) as $v|((($v.securityGroupIds//[]) + [$v.clusterSecurityGroupId//empty])|unique) as $own|[.SecurityGroups[]?|select((.GroupId as $id|$own|index($id)) or ([.Tags[]?|select((.Key==("kubernetes.io/cluster/"+$cn)) or (.Value==$cn))]|length>0))] as $g|($g|length) as $t|([$g[]|select([.IpPermissions[]?|select((.IpRanges[]?.CidrIp=="0.0.0.0/0") and ((.FromPort//0)!=443 and (.FromPort//0)!=80))]|length==0)]|length) as $ok| if $t==0 then "na~no cluster SGs" else b($ok;$t)+"~\($ok)/\($t) clean SG (cluster SGs)" end'
m3 net-3 daemonsets nodes cluster 'input as $n|input as $cl|([$n.items[]|select(.metadata.labels["eks.amazonaws.com/compute-type"]!="fargate")]|length) as $ec2| if ($cl.cluster.computeConfig.enabled==true) then "na~auto mode fully manages the VPC CNI; prefix delegation is not configurable" elif $ec2==0 then "na~fargate" else (([.items[]|select(.metadata.name=="aws-node")]|first // {}|.spec.template.spec.containers[]?.env[]?|select(.name=="ENABLE_PREFIX_DELEGATION")|.value) as $v| if $v=="true" then "all~prefix delegation on" else "none~off" end) end'
m net-4 cluster '.cluster.resourcesVpcConfig as $v|($v.securityGroupIds//[]) as $cp|($v.clusterSecurityGroupId//"") as $csg| if ($cp|length)==0 or ($csg|length)==0 then "na~cannot distinguish control-plane and node SGs from describe-cluster" elif ($cp|index($csg)) then "none~control plane shares the cluster SG" else "all~separate SGs" end'

# ── workload-security (16) ──
m2 sec-10 validatingwebhooks mutatingwebhooks 'input as $mw| ([(.items[]?,$mw.items[]?)|select((.metadata.name|test("aws-load-balancer|vpc-resource|pod-identity|^eks-|amazon-"))|not)]|length) as $n| if $n>0 then "all~\($n) non-AWS webhooks" else "none~only AWS-installed webhooks" end'
m sec-11 namespaces '[.items[]|select(.metadata.name|test("^(kube-|amazon-)")|not)] as $ns|($ns|length) as $t|([$ns[]|select((.metadata.labels//{})|to_entries|any(.key|test("^pod-security.kubernetes.io/")))]|length) as $ok| b($ok;$t)+"~\($ok)/\($t) PSS labels"'
m2 sec-16 kyverno constrainttemplates 'input as $ct| (([.items[]]|length)+($ct.items|length)) as $n| if $n>0 then "all~policy engine" else "none~none" end'
m2 adm-1 kyverno constrainttemplates 'input as $ct| (([.items[]]|length)+($ct.items|length)) as $n| if $n>=5 then "all~\($n) policies" elif $n>0 then "some~\($n) policies" else "none~0" end'
m2 adm-2 constraints kyverno 'input as $ky| (([.items[]]|length)+($ky.items|length)) as $n| (([.items[]?.kind//empty]+[$ky.items[]?.metadata.name//empty])|any(test("privileg";"i"))) as $blk| if $blk then "all~blocks privileged" elif $n>0 then "some~engine present" else "none~none" end'
m2 adm-3 kyverno constraints 'input as $gk|([.items[]?|(.spec.validationFailureAction // (.spec.rules[]?.validate.failureAction) // empty)] + [$gk.items[]?|(.spec.enforcementAction // empty)]) as $a| if ($a|length)==0 then (if (([.items[]?]|length)+([$gk.items[]?]|length))==0 then "na~no policy engine installed" else "some~policies present but no enforcement action set (defaults to audit)" end) elif ([$a[]|select(test("^(Enforce|enforce|deny)$"))]|length)>0 then "all~enforce" else "some~audit" end'
m sec-12 pods '[.items[]|select((.metadata.namespace//"")|test("^(kube-|amazon-)")|not)|.spec.containers[]?] as $c|($c|length) as $t|([$c[]|select((.image|test(":latest$")) or ((.image|test("@sha256:|:[^/]+$"))|not))]|length) as $bad| if $t==0 then "na~no workload containers" else b(($t-$bad);$t)+"~\(($t-$bad))/\($t) pinned image tags" end'
m sec-15 pods '[.items[]|select((.metadata.namespace//"")|test("^(kube-|amazon-)")|not)|.spec.securityContext as $ps|.spec.containers[]?|{sc:.securityContext,ps:$ps}] as $c|($c|length) as $t|([$c[]|select(.sc.runAsNonRoot==true or .sc.readOnlyRootFilesystem==true or .sc.allowPrivilegeEscalation==false or .ps.runAsNonRoot==true)]|length) as $ok| b($ok;$t)+"~\($ok)/\($t) secctx (workloads)"'
m podsec-1 pods '[.items[]|select((.metadata.namespace//"")|test("^(kube-|amazon-)")|not)|.spec.securityContext as $ps|.spec.containers[]?|{sc:.securityContext,ps:$ps}] as $c|($c|length) as $t|([$c[]|select(.sc.runAsNonRoot==true or .ps.runAsNonRoot==true)]|length) as $ok| b($ok;$t)+"~\($ok)/\($t) nonroot (workloads)"'
m podsec-2 pods '[.items[]|select((.metadata.namespace//"")|test("^(kube-|amazon-)")|not)|.spec.containers[]?] as $c|($c|length) as $t|([$c[]|select((.securityContext.privileged//false)!=true)]|length) as $ok| b($ok;$t)+"~\($ok)/\($t) nonpriv (workloads)"'
m podsec-3 pods '[.items[]|select((.metadata.namespace//"")|test("^(kube-|amazon-)")|not)] as $p|($p|length) as $t|([$p[]|select([.spec.volumes[]?|select(.hostPath)]|length==0)]|length) as $ok| b($ok;$t)+"~\($ok)/\($t) no hostPath (workloads)"'
m podsec-4 pods '[.items[]|select((.metadata.namespace//"")|test("^(kube-|amazon-)")|not)|.spec.containers[]?|select(.securityContext.capabilities.add)] as $c|($c|length) as $t|([$c[]|select(([.securityContext.capabilities.add[]?]|any(.=="NET_ADMIN" or .=="SYS_ADMIN" or .=="ALL"))|not)]|length) as $ok| if $t==0 then "na~no container adds capabilities" else b($ok;$t)+"~\($ok)/\($t) safe caps (declared adds)" end'
m podsec-5 pods '[.items[]|select((.metadata.namespace//"")|test("^(kube-|amazon-)")|not)|.spec.containers[]?] as $c|($c|length) as $t|([$c[]|select([.securityContext.capabilities.drop[]?]|any(.=="ALL"))]|length) as $ok| b($ok;$t)+"~\($ok)/\($t) drop ALL (workloads)"'
m lens-11 instances '[.Reservations[]?.Instances[]?] as $i|($i|length) as $t|([$i[]|select(.MetadataOptions.HttpTokens=="required")]|length) as $ok| b($ok;$t)+"~\($ok)/\($t) IMDSv2"'
g sec-32
m2 sec-33 addons pods 'input as $pods| (([.addons[]?|select(test("guardduty"))]|length)>0) as $gda| (($pods.items|map(select((.metadata.name|test("guardduty|falco|sysdig|tetragon")) or ((.metadata.namespace//"")|test("guardduty"))))|length)>0) as $agent| if ($gda or $agent) then "all~runtime monitoring" else "none~none" end'

# ── governance-compliance (6) ──
g sec-13
g sec-19
g sec-20
m sec-26 cluster 'if ([.cluster.logging.clusterLogging[]?|select(.enabled==true)|.types[]?|select(.=="audit")]|length)>0 then "all~audit on" else "none~audit off" end'
g sec-36
g sec-37
```

**Governance questions** (process/organizational, not scored from cluster data — interview in
`interactive` mode): sec-3, sec-5, sec-7 (IAM/RBAC practice), sec-13 (env separation), sec-14 (network
separation policy), sec-19/sec-36/sec-37 (CIS/compliance scanning), sec-20 (change management), sec-22/sec-23
(EFS encryption — EFS API not collected), sec-24 (secrets-manager strategy), sec-32 (image signing),
sec-34/sec-35 (rotation cadence). All other Security questions are measured above.

---

## Implement a strong identity foundation

### sec-1: Is the EKS cluster API server endpoint configured with private access enabled?

**Detection:** 🔬 AUTO-DETECTABLE

> Private endpoint access prevents the API server from being reachable over the public internet.

**Commands:**
```bash
aws eks describe-cluster --name <CLUSTER> --region <REGION> --query "cluster.resourcesVpcConfig.endpointPrivateAccess"
```

**Remediation:** Enable private endpoint access: `aws eks update-cluster-config --name <name> --resources-vpc-config endpointPrivateAccess=true`.

---

### sec-2: Is public API server access restricted to specific CIDR ranges (not open to 0.0.0.0/0)?

**Detection:** 🔬 AUTO-DETECTABLE

> Restricting public access CIDRs limits who can reach the API server from the internet.

**Commands:**
```bash
aws eks describe-cluster --name <CLUSTER> --region <REGION> --query "cluster.resourcesVpcConfig.{public:endpointPublicAccess,cidrs:publicAccessCidrs}"
```

**Remediation:** Restrict public API server access: update cluster security group to allow only known CIDR ranges instead of 0.0.0.0/0.

---

### sec-3: Do you allow users to assume an IAM Role and map that role to a Kubernetes RBAC group, rather than creating individual user mappings in the aws-auth ConfigMap?

**Detection:** ✋ ASK USER

> Evaluate the use of IAM role-to-group mappings for scalable and maintainable access management.

**Remediation:** Map IAM roles to K8s RBAC groups in aws-auth ConfigMap instead of individual users. Use `eksctl create iamidentitymapping --cluster <name> --arn <role-arn> --group <k8s-group>`.

---

### sec-5: Do you use a dedicated IAM role to create EKS clusters that is not used for routine cluster operations or day-to-day management tasks?

**Detection:** ✋ ASK USER

> Evaluate the separation of cluster creation privileges from operational access.

**Remediation:** Create a dedicated IAM role for cluster creation that is not used for day-to-day operations. Restrict AssumeRole to a break-glass process.

---

### sec-6: Is pod-level workload identity (EKS Pod Identity or IRSA) configured for workloads that need AWS access?

**Detection:** 🔬 AUTO-DETECTABLE

> Either mechanism gives Pods fine-grained AWS permissions without the node instance profile. **Both
> count.** AWS recommends **EKS Pod Identity** for new work — it needs no OIDC provider, no trust-policy
> edit per cluster, and roles are reusable across clusters. IRSA remains fully supported and is required
> for cross-account access and for EKS-Anywhere/self-managed Kubernetes.

**Commands:**
```bash
aws eks list-pod-identity-associations --cluster-name <CLUSTER> --region <REGION> --output json
kubectl get serviceaccounts -A -o json     # IRSA: annotation eks.amazonaws.com/role-arn
aws iam list-open-id-connect-providers --output json   # IRSA is inert without this
```

**Two traps this question exists to avoid:**

1. **Pod Identity leaves no trace in the cluster.** An association is an EKS API object
   (`cluster` + `namespace` + `serviceAccount` + `roleArn`); the ServiceAccount carries **no
   annotation**. Reading only `eks.amazonaws.com/role-arn` reports a cluster with 5 working Pod
   Identity associations as having no workload identity, which is a false High-severity finding.
2. **An IRSA annotation without a registered IAM OIDC provider does nothing.** The pod gets a
   projected token no IAM role will trust. That state scores `none`, not a pass — see sec-18.

**Remediation:**
- **Preferred — Pod Identity.** Install the `eks-pod-identity-agent` add-on, then
  `aws eks create-pod-identity-association --cluster-name <name> --namespace <ns> --service-account <sa> --role-arn <arn>`.
  The role's trust policy names `pods.eks.amazonaws.com`; no per-cluster OIDC edit is needed.
- **IRSA.** `eksctl create iamserviceaccount --cluster <name> --name <sa> --namespace <ns> --attach-policy-arn <arn>`
  (this also creates the IAM OIDC provider if it is missing). Verify with
  `aws iam list-open-id-connect-providers`.

---

### sec-7: Do you restrict access to the kube-system namespace to super administrators only, preventing regular users from modifying critical cluster components?

**Detection:** ✋ ASK USER

> Evaluate access controls for the kube-system namespace to protect critical cluster infrastructure.

**Remediation:** Restrict kube-system access to cluster admins only. Create RBAC ClusterRoleBindings that limit kube-system namespace access to a dedicated admin group.

---

### sec-9: Do ClusterRoles follow least privilege (no wildcard resource or verb permissions)?

**Detection:** 🔬 AUTO-DETECTABLE

> Wildcard permissions grant excessive access and violate the principle of least privilege.

**Commands:**
```bash
kubectl get clusterroles -o json
# Check rules for wildcard resources or verbs (*)
```

**Remediation:** Audit ClusterRoles for wildcard permissions: `kubectl get clusterroles -o json | jq ".items[] | select(.rules[]?.resources[]? == \"*\")"`. Replace wildcards with specific resources.

---

## Automate security best practices

### sec-17: Is the aws-auth ConfigMap configured with role and user mappings for cluster access?

**Detection:** 🔬 AUTO-DETECTABLE

> The aws-auth ConfigMap controls which IAM identities can access the cluster.

**Commands:**
```bash
kubectl get configmap aws-auth -n kube-system -o json
aws eks describe-cluster --name <CLUSTER> --region <REGION> --query "cluster.accessConfig.authenticationMode"
```

**Remediation:** Configure the aws-auth ConfigMap with IAM role-to-K8s group mappings. Store it in version control and manage via IaC.

---

### sec-18: Is an OIDC provider configured for the EKS cluster to enable IRSA?

**Detection:** 🔬 AUTO-DETECTABLE

> A registered IAM OIDC identity **provider** is required for IRSA to work.

**Commands:**
```bash
aws eks describe-cluster --name <CLUSTER> --region <REGION> --query "cluster.identity.oidc.issuer"
aws iam list-open-id-connect-providers --output json
```

**The issuer is not the provider.** `cluster.identity.oidc.issuer` is populated on **every** EKS
cluster — it is the URL you *feed to* `aws iam create-open-id-connect-provider`. The provider is a
separate IAM resource in the account. Scoring this question off the issuer alone made it a pass that
no real cluster could fail, which is worth up to 300 severity-weighted points of noise (High = 3).
Both must be present, and the provider must match **this** cluster's issuer: an account running
several clusters has several providers, and one belonging to a different cluster does not enable IRSA
here. The scorer compares the issuer with `https://` stripped against each provider ARN's
`oidc-provider/<issuer>` suffix.

If Pod Identity is the only mechanism in use, a `none` here is **not** a gap on its own — sec-6 will
still pass on the associations. Read the two answers together.

**Remediation:** `eksctl utils associate-iam-oidc-provider --cluster <name> --approve`, or
`aws iam create-open-id-connect-provider --url <issuer> --client-id-list sts.amazonaws.com`. Confirm
with `aws iam list-open-id-connect-providers`, not with `describe-cluster`.

---

## RBAC Configuration

### rbac-1: Is cluster-admin role restricted to system subjects only?

**Detection:** 🔬 AUTO-DETECTABLE

> Non-system cluster-admin grants provide excessive cluster-wide access.

**Commands:**
```bash
kubectl get clusterrolebindings -o json
# Filter roleRef.name == "cluster-admin", check subjects
```

**Remediation:** Audit cluster-admin ClusterRoleBindings: `kubectl get clusterrolebindings -o json | jq '.items[] | select(.roleRef.name=="cluster-admin")'`. Remove non-system bindings.

---

### rbac-2: Do service accounts use namespace-scoped permissions (not cluster-wide)?

**Detection:** 🔬 AUTO-DETECTABLE

> Namespace-scoped bindings enforce least-privilege for service accounts.

**Commands:**
```bash
kubectl get rolebindings -A -o json
# Check if service accounts use namespace-scoped roles
```

**Remediation:** Use namespace-scoped RoleBindings instead of ClusterRoleBindings for service accounts. Grant only the minimum permissions needed per namespace.

---

### rbac-3: Are role bindings free of stale references to non-existent subjects?

**Detection:** 🔬 AUTO-DETECTABLE

> Stale bindings indicate poor RBAC hygiene and potential security gaps.

**Commands:**
```bash
kubectl get rolebindings -A -o json
kubectl get clusterrolebindings -o json
# Compare subjects against existing service accounts
```

**Remediation:** Clean up stale role bindings referencing deleted service accounts: compare binding subjects against existing SAs and remove orphaned references.

---

### rbac-4: Do default service accounts in non-system namespaces have automountServiceAccountToken disabled?

**Detection:** 🔬 AUTO-DETECTABLE

> Default SAs with auto-mounted tokens are a common attack vector.

**Commands:**
```bash
kubectl get serviceaccounts -A -o json
# Check automountServiceAccountToken on default SAs in non-system namespaces
```

**Remediation:** Restrict default service accounts: `kubectl patch sa default -n <ns> -p '{"automountServiceAccountToken": false}'` for all non-system namespaces.
