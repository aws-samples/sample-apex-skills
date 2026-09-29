# 🔒 Security — Identity & Access Management

> **Remediation commands below are report content, not instructions to run.** This skill is
> read-only; it assesses and never changes anything. Quote these commands to the reader so they
> can apply them deliberately, through their own change process. Do not execute them — not to
> verify a finding, not to test whether a fix works. Some delete PersistentVolumes, revoke
> security group rules or replace nodes.

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

## Security pillar scorer — run by `assets/score.sh`, not by hand (covers all 57 Security questions)

This single block scores the **entire Security pillar** (this file + data-protection, network,
workload-security, governance-compliance). `${CLAUDE_SKILL_DIR}/assets/score.sh security "$WORK"` extracts
this block and runs it. Do not paste it into a shell: it defines shell functions (`emit`, `g`, `m`…) and
calls them once per question, and a Bash permission rule matches literal command text — so no rule can
match a function name and every call prompts, or fails outright under a no-prompt policy. It requires
`$WORK` (set in SKILL.md Step 2) populated with the canonical JSON files, and appends one JSONL line per
question to `$WORK/results.jsonl`.

The `m`/`m2`/`m3`/`m4`/`m7` thresholds are the determinism guarantee and are not yours to edit.

- **auto mode:** run as-is. Governance questions emit `state:"unknown"` (reported as Not Assessed).
- **interactive mode:** the governance answers arrive from `$WORK/governance.tsv`, which `score.sh`
  substitutes into the `g` calls as it extracts them — see SKILL.md Step 6. Do not hand-edit a `g` call.

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
# Seven inputs, for `sec-4` alone: NetworkPolicy enforcement is opt-in on BOTH cluster shapes, and the
# two opt-ins are recorded in different places, so the question needs the NetworkPolicy objects, the
# namespaces that form its denominator, and then FIVE separate files of enforcement evidence — the
# aws-node DaemonSet and the add-on list (standard clusters), the `amazon-vpc-cni` ConfigMap and the
# NodeClasses (EKS Auto Mode), and nodes.json to decide which cluster shape it is looking at.
# A copy of `m4`, extended: same abort-on-jq-failure semantics, same `emit` call, same `$B` prelude.
# THE SEQUENCE SKIPS `m5` AND `m6` DELIBERATELY. Nothing in this block takes 5 or 6 files, and a
# helper with no caller is dead code the next reader has to verify by hand before they can trust it.
# Add one when a question needs one, not in anticipation.
#
# ⚠️ THE HELPER NAME IS A CONTRACT WITH THREE FILES THIS BLOCK DOES NOT OWN, AND `m7` CURRENTLY BREAKS
# IT. Two of them hardcode the arity alternation `m[234]?`, so ANY helper above arity 4 -- m5, m6 or m7
# alike -- falls out of their scan silently:
#   assets/render-report.py:524  `_HELPER_ARITY = {"m": 1, "m2": 2, "m3": 3, "m4": 4}`
#   assets/render-report.py:541  `re.match(r"^(m[234]?)\s+([a-z]+-\d+)\s+(.*)$", line)`
#     -> scorer_provenance() drops sec-4 entirely, so its report panel loses "Data read", "Exact
#        command used" and "Returned" -- the audit trail, on a High-severity finding.
#   test-harness/validate-render.sh:552  `re.match(r"\s*m[234]?\s+([a-z]+-\d+)\s", line)`
#     -> gate 5h stops counting sec-4 as measured, so a `Detection:` tag contradicting the scorer would
#        no longer be caught for this question.
# The fix is one entry and one character class, and it belongs to the owners of those files:
# add `"m7": 7` to `_HELPER_ARITY` and widen both regexes to `m\d*`. It is NOT optional -- until it
# lands, sec-4 ships without provenance. Verify with: every id matched by `^m\d*\s+<id>\s` in
# references/ must appear in `scorer_provenance()`; today 103 scorer lines produce 102 entries.
# Neither gate catches this on its own: validate-render.sh's 5c compares label counts against the
# MEASURED total (103) while the report renders 108 panels, so one missing trio hides in the slack.
m7(){ local id="$1" f1="$2" f2="$3" f3="$4" f4="$5" f5="$6" f6="$7" f7="$8" p="$9" r st d; r=$(jq -r "$B $p" "$W/$f1.json" "$W/$f2.json" "$W/$f3.json" "$W/$f4.json" "$W/$f5.json" "$W/$f6.json" "$W/$f7.json" 2>&1) || { printf 'SCORER ABORT [%s]: jq failed — a missing or malformed collection file is NOT a finding, and must never be scored as one. jq said: %s\n' "$id" "$r" >&2; exit 1; }; [ -n "$r" ] || { printf 'SCORER ABORT [%s]: jq produced no output\n' "$id" >&2; exit 1; }; st="${r%%~*}"; d="${r#*~}"; [ "$r" = "$st" ]&&d=""; emit "$id" measured "${st:-none}" "$d"; }

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
# rbac-1 reads aws-auth AS WELL AS the ClusterRoleBindings. `system:masters` is a built-in group whose
# cluster-admin power is baked into the API server: it needs no ClusterRoleBinding at all. That is why
# this check correctly filters it out as a built-in SUBJECT, and exactly why it could not see who
# aws-auth maps INTO it. `awsauth.json` was already collected for this reason — collect.sh: "An entry
# granting system:masters is a full-cluster takeover path via IAM that no RBAC check can see" — and no
# scorer read it, so a cluster handing cluster-admin to an IAM role reported `all~system-only`.
# PRESENCE, NOT A COUNT. `data.mapRoles`/`data.mapUsers` are YAML DOCUMENTS carried as JSON strings and
# jq cannot parse YAML. A substring test over the text is robust; splitting it into entries to count or
# attribute them is not, and a fragile number on a High-severity question is worse than an honest
# boolean. The detail therefore carries no `N/M` — the renderer's extractor produces no matching count,
# so `resource_agreement()` must stay at None (it lists the mappings without cross-checking a total).
# The renderer's `_res_rbac1` twin does attribute ARNs textually so the reader sees which principal is
# involved, and says that it did so; the verdict here does not depend on that attribution.
# ONLY `system:masters` IS MATCHED, deliberately not `cluster-admin`. A group named `cluster-admin`
# grants nothing unless a ClusterRoleBinding binds it — and if one does, the `$ns` clause below already
# reports it as a nonsystem subject. Matching the bare string would instead fire on role ARNs such as
# `.../eks-cluster-admin-role`, which grant nothing by being named that.
# A cluster on `API` auth mode has no aws-auth ConfigMap at all; collect.sh writes `{"items":[]}` for a
# missing optional file, so `.data` is null, the test is false, and this behaves exactly as it did
# before. Absent aws-auth is never itself a finding.
m2 rbac-1 clusterrolebindings awsauth 'input as $aa|(($aa.data.mapRoles//"")+"\n"+($aa.data.mapUsers//"")) as $am|($am|test("system:masters")) as $iam|[.items[]|select(.roleRef.name=="cluster-admin")] as $bb|([$bb[]|.subjects[]?|select(((.name//"")|test("^system:|^eks:"))|not)|select(.name!="system:masters")]|length) as $ns| if $iam then "none~kube-system/aws-auth maps an IAM principal into system:masters (matched in data.mapRoles/mapUsers) — cluster-admin granted through IAM, which no ClusterRoleBinding can show"+(if $ns>0 then ", plus \($ns) nonsystem cluster-admin subject(s) in ClusterRoleBindings" else "" end) elif ($bb|length)==0 then "na~none" elif $ns==0 then "all~system-only" else "none~\($ns) nonsystem" end'
m2 rbac-2 rolebindings clusterrolebindings 'input as $crb|[.items[]?|select(((.metadata.namespace//"")|test("^(kube-|amazon-)"))|not)|(.metadata.namespace//"") as $bns|.subjects[]?|select(.kind=="ServiceAccount")|(((.namespace//$bns)|if .=="" then $bns else . end)+"/"+.name)]|unique as $ns_bound|[$crb.items[]?|select(((.metadata.name//"")|test("^(system:|eks:)"))|not)|.subjects[]?|select(.kind=="ServiceAccount")|select(((.namespace//"")|test("^(kube-|amazon-)"))|not)|((.namespace//"")+"/"+.name)]|unique as $cluster_bound|(($ns_bound+$cluster_bound)|unique|length) as $t|(($ns_bound-$cluster_bound)|length) as $ok| if $t==0 then "na~no workload ServiceAccount bindings" else b($ok;$t)+"~\($ok)/\($t) SAs namespace-scoped only" end'
m2 rbac-3 rolebindings serviceaccounts 'input as $sa| ($sa.items|map(.metadata.namespace+"/"+.metadata.name)) as $known|[.items[]?|select(((.metadata.namespace//"")|test("^(kube-|amazon-)"))|not)|(.metadata.namespace//"") as $bns|.subjects[]?|select(.kind=="ServiceAccount")|(((.namespace//$bns)|if .=="" then $bns else . end)+"/"+.name)] as $refs|($refs|length) as $t|([$refs[]|select(. as $r|$known|index($r))]|length) as $ok| if $t==0 then "na~no workload SA bindings" else b($ok;$t)+"~\($ok)/\($t) resolve" end'
# rbac-4 covers EVERY workload ServiceAccount, not only the one literally named `default`. Real workloads
# use named SAs, so the old check was blind to the normal case. It also reports pod-level
# `automountServiceAccountToken: true`, which overrides an SA-level `false` -- so the SA can look
# compliant while the pods still receive a token.
m2 rbac-4 serviceaccounts pods 'input as $p|[.items[]?|select((.metadata.namespace//"")|test("^(kube-|amazon-)")|not)] as $sa|($sa|length) as $t|([$sa[]|select(.automountServiceAccountToken==false)]|length) as $ok|([$p.items[]?|select(.spec.automountServiceAccountToken==true)]|length) as $override| if $t==0 then "na~no workload ServiceAccounts" elif $override>0 then b($ok;$t)+"~\($ok)/\($t) SAs disable token automount, but \($override) pod(s) re-enable it in their own spec (a pod-level true overrides the SA)" else b($ok;$t)+"~\($ok)/\($t) SAs disable token automount" end'

# ── data-protection (11) ──
m sec-8 deployments 'if ([.items[]|select(.metadata.name|test("external-secrets"))]|length)>0 then "all~ESO present" else "none~no ESO" end'
g sec-24
g sec-34
g sec-35
# sec-21 also matches `ebs.csi.aws.com/cluster-name`, the tag AWS's own cluster-scoped CSI policy uses.
# And critically: it no longer answers `na` when EBS-backed PersistentVolumes exist but nothing carries a
# cluster tag. Dynamically-provisioned CSI volumes get a cluster tag only when the driver is configured
# to add one, so a High-severity encryption check was reporting "not applicable" on clusters that
# demonstrably had EBS volumes. `na` is excluded from scoring entirely, so that was a silent pass.
#
# THE PV FALLBACK MATCHES EKS AUTO MODE'S CSI DRIVER TOO. `.spec.csi.driver` was tested against
# `ebs.csi.aws.com` only, and Auto Mode's driver has a different name:
#   https://docs.aws.amazon.com/eks/latest/userguide/create-storage-class.html
#   "You must create a `StorageClass` referencing `ebs.csi.eks.amazonaws.com` to use the storage
#   capability of EKS Auto Mode"
# So the "NOT SCOPED" branch — which exists precisely to stop this question answering from too little
# evidence — was blind on exactly the clusters that need it. This is not hypothetical: on the real Auto
# Mode cluster in this account, before the collector learned to recover Auto-Mode-hidden volumes by id,
# sec-21 published `all~1/1 encrypted` on a cluster that had SEVEN volumes. Full confidence off one
# seventh of the data. The collector fixed the numerator; this fixes the branch that is supposed to
# notice when the denominator is missing.
#
# AUTO MODE FULFILS THE NODE HALF OF THIS QUESTION AND NOT THE PV HALF, so the detail says which is
# which rather than reading as a blanket pass. AWS's own security whitepaper, on the node half:
#   https://docs.aws.amazon.com/whitepapers/latest/security-overview-amazon-eks-auto-mode/eks-auto-mode-data-plane.html
#   "On EKS Auto Mode nodes, the root and data Amazon EBS volumes are encrypted and configured to be
#   deleted upon termination of the instance"
# and the User Guide, on the PV half, in the same breath as stating the boundary — "EKS Auto Mode
# manages the volumes attached to EC2 instances at creation time, including root and data volumes. EKS
# Auto Mode does not fully manage EBS volumes created using Kubernetes persistent storage features":
#   https://docs.aws.amazon.com/eks/latest/userguide/auto-security.html
#   "AWS recommends that you enable encryption for EBS Volumes provisioned by Kubernetes persistent
#   storage features"
# The clause is appended, never substituted, and carries no second ratio: `_res_volumes` in
# render-report.py cross-checks the LEADING `\($ok)/\($t)`, which is unchanged.
# The Auto Mode test is EVERY EC2 NODE carrying the documented label, not `computeConfig.enabled` —
# see the argument at sec-30 and at references/reliability.md's lens-2. On a hybrid cluster the
# managed-node-group root volumes are the operator's, so no node-half credit is claimed there.
m4 sec-21 volumes cluster pv nodes 'input as $cl|input as $pvs|input as $nd|($cl.cluster.name//"") as $cn|[$nd.items[]?|select((.metadata.labels["eks.amazonaws.com/compute-type"]//"")!="fargate")] as $ec2|($ec2|length) as $nt|([$ec2[]|select((.metadata.labels["eks.amazonaws.com/compute-type"]//"")=="auto")]|length) as $nauto|(($cl.cluster.computeConfig.enabled==true) and $nt>0 and $nauto==$nt) as $allauto|[.Volumes[]?|select([.Tags[]?|select((.Key==("kubernetes.io/cluster/"+$cn)) or (((.Key|ascii_downcase)|test("cluster")) and (.Value==$cn)))]|length>0)] as $v|($v|length) as $t|([$v[]|select(.Encrypted==true)]|length) as $ok|([$pvs.items[]?|select(.spec.csi.driver=="ebs.csi.aws.com" or .spec.csi.driver=="ebs.csi.eks.amazonaws.com" or (.spec.awsElasticBlockStore!=null))]|length) as $ebspv|(if $allauto then " — every EC2 node is an EKS Auto Mode node, so the root and data volumes AWS attaches at launch are encrypted by design; the volumes Kubernetes persistent storage provisions stay yours to encrypt (sec-25)" else "" end) as $am| if $t==0 and $ebspv>0 then "none~NOT SCOPED: \($ebspv) EBS-backed PersistentVolume(s) exist but no volume carries a cluster tag, so encryption could not be checked — tag them (ebs.csi.aws.com/cluster-name or kubernetes.io/cluster/<name>) and re-run" elif $t==0 then "na~no cluster-tagged volumes and no EBS-backed PVs" else b($ok;$t)+"~\($ok)/\($t) encrypted (cluster vols)"+$am end'
# sec-38 measures whether a CUSTOMER-MANAGED key is in use -- not whether envelope encryption exists.
# The distinction is the whole finding. AWS envelope-encrypts all Kubernetes API data, Secrets included,
# by default on 1.28+ with an AWS-owned KMS key, and says it "doesn't require any action on your part";
# every version in standard or extended support today is >= 1.31, so the default is universal. This check
# used to emit "no envelope encryption", which told every cluster without a CMK that a control AWS
# documents as on was absent -- a false finding on 100% of clusters, and one that pushed the reader
# toward an irreversible change. What is genuinely absent is the key policy, the CloudTrail trail and
# revocation control that come with bringing your own key.
#   https://docs.aws.amazon.com/eks/latest/userguide/envelope-encryption.html
# `resources` is deprecated for the same reason (it "no longer affects which resources are encrypted"),
# but AWS still returns ["secrets"] to preserve the old API contract, so matching on it is safe.
m sec-38 cluster '([.cluster.encryptionConfig[]?|select((.resources//[])|index("secrets"))]|first) as $ec| if $ec==null then "none~no customer-managed KMS key: Secrets are envelope-encrypted with the default AWS-owned key, so the key policy, CloudTrail audit trail and revocation are not yours to control" elif (($ec.provider.keyArn//"")|length)>0 then "all~Secrets encrypted with customer-managed KMS key" else "some~encryptionConfig covers secrets but names no keyArn" end'
g sec-22
# sec-25's provisioner set is CANONICAL and MUST stay character-identical to the two other copies:
# `_res_storageclasses` in assets/render-report.py and `cost-9` in references/cost-optimization.md.
# EDIT ALL THREE OR NONE. All three names must remain: `ebs.csi.aws.com` (self-managed EBS CSI driver),
# `ebs.csi.eks.amazonaws.com` (EKS Auto Mode) and `kubernetes.io/aws-ebs` (in-tree legacy).
#   https://docs.aws.amazon.com/eks/latest/userguide/create-storage-class.html
#   "EKS Auto Mode does not create a `StorageClass` for you. You must create a `StorageClass`
#   referencing `ebs.csi.eks.amazonaws.com` to use the storage capability of EKS Auto Mode"
# The Auto Mode name was missing, so this weight-2 question answered `na~no EBS StorageClass` on an Auto
# Mode cluster that HAD one — and `na` is excluded from scoring, so an unencrypted Auto Mode
# StorageClass took no penalty and got no mention. THE VERDICT IS UNCHANGED BY INTENT: the StorageClass
# is entirely the operator's object on Auto Mode (auto-security.html: "AWS recommends that you enable
# encryption for EBS Volumes provisioned by Kubernetes persistent storage features"), so this is a
# detection fix, not a credit — Auto Mode gets no pass here, it merely stops being invisible.
# THE OLD SET WAS WRONG IN BOTH DIRECTIONS ON A REAL AUTO MODE CLUSTER, which typically carries the
# legacy in-tree `gp2` class alongside the Auto Mode one. Measured against a live cluster's two
# StorageClasses -- `auto-ebs-sc` (ebs.csi.eks.amazonaws.com, encrypted=true) and `gp2`
# (kubernetes.io/aws-ebs, encrypted unset) -- the old regex answered `none~0/1`: it counted ONLY the
# unencrypted legacy class and could not see the encrypted Auto Mode one, so it named the right
# problem for the wrong reason and would have gone on doing so if the operator encrypted the Auto Mode
# class. The corrected set answers `some~1/2`, which is the honest reading: one EBS StorageClass on the
# cluster still provisions unencrypted volumes.
m sec-25 storageclasses '[.items[]|select((.provisioner//"")|test("ebs\\.csi\\.aws\\.com|ebs\\.csi\\.eks\\.amazonaws\\.com|kubernetes\\.io/aws-ebs"))] as $s|($s|length) as $t|([$s[]|select(.parameters.encrypted=="true")]|length) as $ok| if $t==0 then "na~no EBS StorageClass" else b($ok;$t)+"~\($ok)/\($t) encrypted EBS SC" end'
g sec-23
# sec-27 and rel-16 answer the same question -- "is a service mesh present?" -- and used to disagree on
# the same cluster: rel-16 credited Consul Connect and sec-27 did not, while sec-27 matched the namespaces
# istio-system|linkerd and rel-16 did not. So a Consul cluster scored `most` in Reliability and `none` in
# Security, and a mesh with renamed control-plane Deployments in namespace `linkerd` scored the reverse.
# Both patterns were half right; this is their union. EDIT BOTH OR NEITHER -- rel-16 is at
# references/reliability.md:78 and nothing enforces their agreement.
m sec-27 deployments 'if ([.items[]?|select(((.metadata.namespace//"")|test("istio-system|linkerd|consul";"i")) or (.metadata.name|test("istiod|linkerd|consul-connect";"i")))]|length)>0 then "all~mesh present" else "none~no mesh" end'
# sec-28 asks whether mTLS is ENFORCED. Sidecar presence does not establish that: Istio's default mesh
# mode is PERMISSIVE, which accepts plaintext alongside mTLS. STRICT requires a PeerAuthentication, so
# that object is now collected and required for a pass; sidecars without it score `some`.
# sec-28 can only speak to Istio and Linkerd. Its evidence is the sidecar name plus an Istio
# PeerAuthentication; Consul's sidecar is `envoy-sidecar`/`consul-dataplane` and its enforcement lives in
# ProxyDefaults/ServiceDefaults CRDs that collect.sh does not gather. Since sec-27 now credits Consul as a
# mesh, reporting "no mesh sidecars" on a Consul cluster would contradict sec-27 one question later --
# the same disagreement, moved. A Consul mesh therefore answers `na` with the reason, which keeps it out
# of the score entirely rather than scoring a control this data cannot see.
m2 sec-28 pods peerauthentications 'input as $pa|[.items[]?|select((.metadata.namespace//"")|test("^(kube-|amazon-)")|not)] as $p|($p|length) as $t|([$p[]|select([.spec.containers[]?.name]|any(test("istio-proxy|linkerd-proxy")))]|length) as $inj|([$p[]|select([.spec.containers[]?.name]|any(test("envoy-sidecar|consul-dataplane")))]|length) as $consul|([$pa.items[]?|select((.spec.mtls.mode//"")=="STRICT")]|length) as $strict| if $t==0 then "na~no workload pods" elif ($inj==0 and $consul>0) then "na~\($consul)/\($t) pods carry a Consul sidecar; Consul enforcement lives in ProxyDefaults/ServiceDefaults, which this review does not collect, so mTLS mode is NOT ASSESSED rather than absent" elif $inj==0 then "none~no mesh sidecars" elif $strict==0 then "some~\($inj)/\($t) pods have a mesh sidecar but no PeerAuthentication sets STRICT, so plaintext is still accepted (Istio defaults to PERMISSIVE)" else b($inj;$t)+"~\($inj)/\($t) pods meshed, STRICT mTLS enforced by \($strict) PeerAuthentication(s)" end'
# sec-29 reads Ingress only, so its `na` means "no Ingress objects" -- NOT "nothing is exposed in
# plaintext". A cluster fronting its apps with a Service of type LoadBalancer on port 80 has real
# in-transit exposure and no Ingress, and would land here. services.json is collected (lens-9 reads it),
# so widening this to cover LoadBalancer listeners is possible and is the right long-term fix; until then
# the `na` says what was and was not examined, so the report cannot imply the question was answered.
m sec-29 ingresses '[.items[]] as $i|($i|length) as $t|([$i[]|select((.spec.tls//[])|length>0)]|length) as $ok| if $t==0 then "na~no Ingress objects; TLS on Service type=LoadBalancer is not assessed, so this is not a finding of no plaintext exposure" else b($ok;$t)+"~\($ok)/\($t) TLS" end'

# ── network (8) ──
# sec-4 checks that NetworkPolicies can actually be ENFORCED, not merely that objects exist. Enforcement
# is opt-in, in the service documentation's own words:
# docs.aws.amazon.com/eks/latest/userguide/cni-network-policy-configure.html -- "You must configure the
# following in order to use this feature: 1. Set up policy enforcement at Pod startup. You do this in the
# `aws-node` container of the VPC CNI DaemonSet. 2. Enable the network policy parameter for the add-on.
# 3. Configure your cluster to use the Kubernetes network policy." So on a cluster where none of the
# three was done, every NetworkPolicy object is inert, and this High-severity question used to score
# `all` while nothing was enforced. (An earlier draft of this comment quoted a 2023 launch blog post's
# "disabled by default at launch" phrasing; the User Guide states the same requirement and is the source
# that tracks the service, so the blog quote is gone.) Enforcement shows up as the `aws-eks-nodeagent`
# container in the aws-node DaemonSet (added when enableNetworkPolicy is on) or an explicit
# NETWORK_POLICY_ENFORCING_MODE env var. Both are
# already collected -- net-3 reads this same DaemonSet's env. A third-party enforcing CNI (Calico,
# Cilium) replaces vpc-cni entirely, so the guard only fires when vpc-cni IS the installed addon.
#
# THE STANDARD-CLUSTER GUARD ABOVE CANNOT FIRE ON EKS AUTO MODE, AND THAT WAS THE WHOLE FAILURE.
# It is conditioned on the `vpc-cni` add-on being installed and on an `aws-eks-nodeagent` container in
# the `aws-node` DaemonSet. An all-Auto-Mode cluster has neither -- no vpc-cni add-on, no aws-node
# DaemonSet at all -- so the guard was structurally unreachable and the raw coverage ratio was
# published, up to `all`, on a cluster where policy enforcement may be entirely off. It returned the
# same answer whether Auto Mode enforced or not, which makes it inert, not satisfied. Auto Mode
# enforcement is OPT-IN, in the service documentation's own words:
#   https://docs.aws.amazon.com/eks/latest/userguide/auto-net-pol.html
#   "To use network policies with EKS Auto Mode, you first need to enable the Network Policy Controller
#   by applying a ConfigMap to your cluster."  (`metadata.name: amazon-vpc-cni`, `namespace:
#   kube-system`, `data.enable-network-policy-controller: "true"`)
#   https://docs.aws.amazon.com/eks/latest/best-practices/autosecure.html
#   "Q: Is Network Policy support enabled by default in EKS Auto Mode? A: For now, Network Policy
#   support needs to be explicitly enabled through the VPC CNI add-on configuration."
# BOTH DOCUMENTED KEYS ARE ACCEPTED. auto-net-pol.html shows `enable-network-policy-controller` and
# autosecure.html shows `enable-network-policy`, in the same ConfigMap, for the same purpose. The pages
# disagree about the key name; refusing to read the one a customer copied out of the other page would
# fail them for following AWS documentation. Either key, set to "true", is the opt-in.
#
# WHAT WE DECIDED ABOUT THE NODECLASS, AND WHY. autosecure.html adds "It's also required to define the
# Network Policy support is configured in the Node Class", with `spec.networkPolicy` on the NodeClass.
# auto-net-pol.html contradicts that: its NodeClass step is titled "Step 3: Adjust Network Policy Agent
# configuration in Node Class (Optional)", the field is commented "# Optional: Changes default network
# policy behavior", and Step 2 -- reached with Step 1's ConfigMap alone -- already says "Your EKS Auto
# Mode cluster is now configured to support Kubernetes network policies." So `spec.networkPolicy` is
# documented as ADJUSTING an agent that the ConfigMap has already switched on, and the only two values
# create-node-class.html gives are `DefaultAllow` and `DefaultDeny` -- both of which are enforcement
# postures, neither of which is "off". Treating an ABSENT `spec.networkPolicy` as a failure would
# manufacture a finding out of a step the User Guide labels Optional; treating `DefaultAllow` as a pass
# would manufacture a credit out of a field that does not enable anything. So the ConfigMap alone
# decides the verdict, and any NodeClass `spec.networkPolicy` value is REPORTED, not scored -- the same
# treatment the standard path already gives NETWORK_POLICY_ENFORCING_MODE. The residual uncertainty is
# recorded rather than hidden: no AWS page states which value `spec.networkPolicy` defaults to when the
# field is unset, so this scorer does not claim to know.
# A LIVE AUTO MODE CLUSTER SETTLED THIS RATHER THAN THE READING ALONE. Captured read-only: the
# `amazon-vpc-cni` ConfigMap does not exist (`Error from server (NotFound)`) while NodeClass `default`
# DOES carry `spec.networkPolicy: DefaultAllow`. So the half an operator actually reaches for is the
# optional one, and had `spec.networkPolicy` been read as the enabling signal this cluster would have
# scored a pass with enforcement off -- doubly wrong, since `DefaultAllow` is the PERMISSIVE mode of the
# two. The not-enforced arm therefore names that exact mistake when it sees it, because "you configured
# step 3 and not step 1" is the actionable sentence and "not enforced" alone is not.
# The arm also has a no-policies variant: with zero covered namespaces, "the NetworkPolicy objects are
# not enforced" is vacuously true and reads as though objects existed, so that case says instead that no
# workload namespace carries one and pod-to-pod traffic is unrestricted. Neither variant prints a ratio.
#
# THE GATE IS EVERY EC2 NODE, NOT `computeConfig.enabled` -- the same re-gating applied to
# references/reliability.md's lens-2, and for the same reason. A hybrid cluster has Auto Mode enabled
# AND an `aws-node` DaemonSet with a live nodeagent, so the flag alone would hand the standard-cluster
# guard's job to an Auto Mode arm that cannot see the mechanism actually enforcing on the managed
# nodes: https://docs.aws.amazon.com/eks/latest/userguide/eks-add-ons.html -- "However, if your cluster
# combines Auto mode with other compute options like self-managed EC2 instances, Managed Node Groups,
# or AWS Fargate, these add-ons remain necessary." Membership is the documented label,
# create-node-pool.html's supported-label table -- "| eks.amazonaws.com/compute-type | auto |
# Identifies EKS Auto Mode managed nodes |" -- and associate-workload.html -- "EKS Auto Mode nodes have
# set the value of the label `eks.amazonaws.com/compute-type` to `auto`." cluster.json is deliberately
# NOT an eighth input: a node cannot carry that label unless Auto Mode is enabled, so once every EC2
# node carries it the cluster flag adds no information. Fargate nodes are excluded from the denominator
# as everywhere else, and an EMPTY EC2 node set does not satisfy the gate ($nt>0 is required) so an
# empty cluster is never vacuously routed down the Auto Mode arm.
# The standard guard now carries `($allauto|not)` so the two guards can never both claim the cluster and
# report contradictory reasons -- on an all-Auto-Mode cluster there is no aws-node DaemonSet for the
# standard guard's evidence to be about. Enforcement mechanism, for the reader: the security whitepaper's
# eks-auto-mode-data-plane.html -- "These policies are enforced by a networking component on the node
# using eBPF."
# NO RATIO IN THE AUTO MODE ARM. `_res_ns_has(d, "networkpolicies")` is this question's extractor and
# resource_agreement() cross-checks a LEADING `n/m`; the standard-cluster guard's ratio already agrees
# with it and is left exactly as it was, and the new arms add none.
m7 sec-4 networkpolicies namespaces daemonsets addons vpccniconfig nodeclasses nodes 'input as $ns|input as $ds|input as $ad|input as $cm|input as $nc|input as $nd|([$ad.addons[]?]|index("vpc-cni")) as $has_cni|([$ds.items[]?|select(.metadata.name=="aws-node")|.spec.template.spec.containers[]?.env[]?|select(.name=="NETWORK_POLICY_ENFORCING_MODE")|.value]|first) as $mode|([$ds.items[]?|select(.metadata.name=="aws-node")|.spec.template.spec.containers[]?|select(.name=="aws-eks-nodeagent")]|length>0) as $agent|[$nd.items[]?|select((.metadata.labels["eks.amazonaws.com/compute-type"]//"")!="fargate")] as $ec2|($ec2|length) as $nt|([$ec2[]|select((.metadata.labels["eks.amazonaws.com/compute-type"]//"")=="auto")]|length) as $nauto|($nt>0 and $nauto==$nt) as $allauto|((($cm.data["enable-network-policy-controller"]//$cm.data["enable-network-policy"]//"")|tostring|ascii_downcase)=="true") as $npc|([$nc.items[]?|select(((.spec.networkPolicy//"")|tostring)!="")|"\(.metadata.name)=\(.spec.networkPolicy)"]|join(", ")) as $ncpol|[$ns.items[]|select(.metadata.name|test("^(kube-|amazon-)")|not)|.metadata.name] as $n|($n|length) as $t|([.items[].metadata.namespace]|unique) as $cov|([$n[]|select(. as $x|$cov|index($x))]|length) as $ok| if $t==0 then "na~no workload namespaces" elif ($allauto and ($npc|not)) then (if $ok>0 then "none~every EC2 node is an EKS Auto Mode node and the amazon-vpc-cni ConfigMap in kube-system does not enable the Network Policy Controller, so the NetworkPolicy objects that exist in this cluster are NOT enforced — Auto Mode enforcement is opt-in and was never opted into" else "none~every EC2 node is an EKS Auto Mode node, the amazon-vpc-cni ConfigMap in kube-system does not enable the Network Policy Controller, and no workload namespace carries a NetworkPolicy — Auto Mode enforcement is opt-in and was never opted into, so pod-to-pod traffic is unrestricted" end) + (if $ncpol!="" then " (NodeClass networkPolicy \($ncpol) IS set, but that is the documented-optional step 3 and it does not enable the controller — apply the ConfigMap)" else "" end) elif ($allauto|not) and ($has_cni != null) and ($agent|not) and ($mode==null) then "none~\($ok)/\($t) ns have a NetworkPolicy, but the VPC CNI network-policy agent is not running so none of them is enforced" else b($ok;$t)+"~\($ok)/\($t) ns with a NetworkPolicy" + (if $mode!=null then " (CNI mode: \($mode))" else "" end) + (if ($allauto and $npc) then " (Auto Mode Network Policy Controller enabled" + (if $ncpol!="" then "; NodeClass networkPolicy \($ncpol), reported not scored" else "" end) + ")" else "" end) + (if (($allauto|not) and $nauto>0 and ($npc|not)) then " — but \($nauto) of \($nt) EC2 nodes are EKS Auto Mode nodes, whose enforcement is gated separately by the amazon-vpc-cni ConfigMap and is not enabled, so no policy is enforced for pods landing there" else "" end) end'
g sec-14
# sec-30 asks whether SSH to the nodes is disabled. On EKS Auto Mode nodes THE SECURITY GROUP IS THE
# WRONG EVIDENCE, because there is no listener for port 22 to reach:
#   https://docs.aws.amazon.com/eks/latest/userguide/auto-security.html
#   "SSH access is not available." / "AWS Systems Manager Session Manager (SSM) access is not
#   available."
#   https://docs.aws.amazon.com/whitepapers/latest/security-overview-amazon-eks-auto-mode/eks-auto-mode-data-plane.html
#   "remote access services like SSH and the AWS Systems Manager agent are not available on Auto Mode
#   nodes"
# and the same page gives the break-glass path the question's own remediation asks for: "NodeDiagnostic
# resource - The NodeDiagnostic custom resource definition (CRD) is a Kubernetes-native method of
# fetching system logs and information from an EKS Auto Mode node." So on an all-Auto-Mode cluster this
# control is met by the platform, and an open port 22 in a cluster security group grants nothing.
# THE GATE IS EVERY EC2 NODE CARRYING THE DOCUMENTED LABEL, matching references/reliability.md's lens-2
# (create-node-pool.html's supported-label table: "| eks.amazonaws.com/compute-type | auto | Identifies
# EKS Auto Mode managed nodes |"; associate-workload.html: "EKS Auto Mode nodes have set the value of
# the label `eks.amazonaws.com/compute-type` to `auto`."). Fargate nodes are excluded from the
# denominator as everywhere else, and $nt>0 is required so a cluster with no nodes is never credited
# vacuously. ON A HYBRID CLUSTER IT FALLS THROUGH to the security-group measurement, because a managed
# node group DOES run sshd and its port 22 is real.
# The rule stays visible to the reader even when credited: the detail names the open-SG rule it is
# declining to apply and points at net-2, which still measures 0.0.0.0/0 on every other port -- so
# "SSH is not reachable" can never be misread as "this security group is fine".
m3 sec-30 sg cluster nodes 'input as $cl|input as $nd|($cl.cluster.name//"") as $cn|($cl.cluster.resourcesVpcConfig) as $v|((($v.securityGroupIds//[]) + [$v.clusterSecurityGroupId//empty])|unique) as $own|[$nd.items[]?|select((.metadata.labels["eks.amazonaws.com/compute-type"]//"")!="fargate")] as $ec2|($ec2|length) as $nt|([$ec2[]|select((.metadata.labels["eks.amazonaws.com/compute-type"]//"")=="auto")]|length) as $nauto|[.SecurityGroups[]?|select((.GroupId as $id|$own|index($id)) or ([.Tags[]?|select((.Key==("kubernetes.io/cluster/"+$cn)) or (.Value==$cn))]|length>0))] as $g| if (($cl.cluster.computeConfig.enabled==true) and $nt>0 and $nauto==$nt) then "all~every EC2 node is an EKS Auto Mode node, where SSH and the SSM agent are not available at all, so port 22 cannot reach a listener and break-glass access is the NodeDiagnostic CRD; the open-security-group rule is therefore not applied here — net-2 still measures 0.0.0.0/0 on every other port" elif ($g|length)==0 then "na~no cluster SGs" elif ([$g[].IpPermissions[]?|select((.IpProtocol=="-1" or ((.FromPort//0)<=22 and (.ToPort//0)>=22)) and (.IpRanges[]?.CidrIp=="0.0.0.0/0"))]|length)>0 then "none~ssh 0.0.0.0/0" else "all~no ssh open (cluster SGs)" end'
# sec-31 asked the same thing net-4 used to: whether control-plane and node security groups are
# separate. net-4 has been RESCOPED to cluster-SG egress, so "deduplicated against net-4" is no longer
# true — nothing measures SG separation now, deliberately, because AWS states the split is "no longer
# required and can be removed". Kept as `na` with an accurate reason rather than deleted, so a reader
# comparing this run against an older report can see why the question stopped being answered.
m sec-31 cluster '"na~retired: AWS no longer recommends separating control-plane and node security groups"'
m2 net-1 subnets cluster 'input as $cl|(($cl.cluster.resourcesVpcConfig.subnetIds)//[]) as $own|[.Subnets[]?|select(($own|length)==0 or (.SubnetId as $id|$own|index($id)))] as $s|($s|length) as $t|([$s[]|select(.AvailableIpAddressCount>=100)]|length) as $ok| if $t==0 then "na~no cluster subnets" else b($ok;$t)+"~\($ok)/\($t) >=100 IPs (cluster subnets)" end'
# net-2 tests the whole port SPAN, not just FromPort. A rule is only clean when it opens exactly
# one of 80/443 to the world — i.e. FromPort==ToPort and that port is 80 or 443. Testing FromPort
# alone let `80-65535 from 0.0.0.0/0` score CLEAN, because FromPort was 80: a security group open
# to almost every port passed a least-privilege check. `-1` (all protocols) carries no ports at
# all and is always dirty. This matches the renderer's _sg_clean twin, which already required
# both ends to be in {80,443} and was therefore reporting a disagreement against this scorer.
m2 net-2 sg cluster 'input as $cl|($cl.cluster.name//"") as $cn|($cl.cluster.resourcesVpcConfig) as $v|((($v.securityGroupIds//[]) + [$v.clusterSecurityGroupId//empty])|unique) as $own|[.SecurityGroups[]?|select((.GroupId as $id|$own|index($id)) or ([.Tags[]?|select((.Key==("kubernetes.io/cluster/"+$cn)) or (.Value==$cn))]|length>0))] as $g|($g|length) as $t|([$g[]|select([.IpPermissions[]?|select((.IpRanges[]?.CidrIp=="0.0.0.0/0") and (.IpProtocol=="-1" or ((.FromPort//0)!=(.ToPort//0)) or ((.FromPort//0)!=443 and (.FromPort//0)!=80)))]|length==0)]|length) as $ok| if $t==0 then "na~no cluster SGs" else b($ok;$t)+"~\($ok)/\($t) clean SG (cluster SGs)" end'
# ECR supply-chain controls, MOVED here from the Cost Optimization scorer: an image registry
# without scan-on-push or tag immutability is a supply-chain exposure, not an overspend, and
# the EKS Best Practices Guides place both under Security / Image Security.
m2 lens-12 ecr pods 'input as $p|[$p.items[].spec.containers[]?.image|select(test("dkr.ecr"))|capture("amazonaws.com/(?<r>[^:@]+)").r] as $used|[.repositories[]?|select(.repositoryName as $rn|$used|index($rn))] as $r|($r|length) as $t|([$r[]|select(.imageScanningConfiguration.scanOnPush==true)]|length) as $ok| if $t==0 then "na~no cluster ECR repos" else b($ok;$t)+"~\($ok)/\($t) scan-on-push" end'
m2 lens-13 ecr pods 'input as $p|[$p.items[].spec.containers[]?.image|select(test("dkr.ecr"))|capture("amazonaws.com/(?<r>[^:@]+)").r] as $used|[.repositories[]?|select(.repositoryName as $rn|$used|index($rn))] as $r|($r|length) as $t|([$r[]|select(.imageTagMutability=="IMMUTABLE")]|length) as $ok| if $t==0 then "na~no cluster ECR repos" else b($ok;$t)+"~\($ok)/\($t) immutable" end'
# net-3 used to answer `na~auto mode fully manages the VPC CNI; prefix delegation is not configurable`
# on any cluster with `computeConfig.enabled`. That detail was wrong twice over. Prefix delegation is
# the documented Auto Mode DEFAULT -- which is exactly what this question wants:
#   https://docs.aws.amazon.com/eks/latest/userguide/auto-networking.html
#   "EKS Auto Mode defaults to using prefix delegation (/28 prefixes) for pod networking and maintains a
#   predefined warm pool of IP resources that scales based on the number of scheduled pods"
# and it IS configurable, so the default must be verified rather than asserted:
#   https://docs.aws.amazon.com/eks/latest/userguide/create-node-class.html
#   "ipv4PrefixSize is default to Auto which is prefix and fallback to secondary IP. \"32\" is the
#   secondary IP mode."
# The field lives at `spec.advancedNetworking.ipv4PrefixSize` in that page's NodeClass specification and
# nowhere else, so only that path is read -- guessing at a second path would be inventing a shape the
# documentation does not describe. nodeclasses.json is now collected, so a NodeClass that opts a cluster
# into secondary-IP mode is reported instead of being credited.
# THE GATE IS EVERY EC2 NODE, NOT `computeConfig.enabled`. On a hybrid cluster the old flag-based `na`
# SUPPRESSED A REAL FINDING: the identical Standard cluster answers `none~off`, while the hybrid one went
# `na` -- excluded from scoring entirely -- even though it provably still runs an `aws-node` DaemonSet
# with `ENABLE_PREFIX_DELEGATION` sitting in its env waiting to be read. Auto Mode capabilities do not
# reach non-Auto-Mode nodes: eks-add-ons.html -- "However, if your cluster combines Auto mode with other
# compute options like self-managed EC2 instances, Managed Node Groups, or AWS Fargate, these add-ons
# remain necessary" -- and auto-networking.html's Important callout says the same of the node-level DNS
# service: "Non-Auto Mode nodes rely on the traditional CoreDNS pods for DNS resolution, as they cannot
# access the node-level DNS service that Auto Mode provides." Same membership test, same $ec2>0
# requirement and same Fargate exclusion as lens-2 and sec-30, so the three gates cannot drift.
# `none` for an `ipv4PrefixSize: "32"` NodeClass is the accurate answer to the question as asked -- is
# prefix delegation enabled -- and NOT automatically a defect. create-node-class.html recommends
# secondary IP mode for pod-sparse workloads at scale, so the remediation prose tells the reader to
# check whether the opt-out was deliberate before changing it. Low severity, so the honest `none` costs
# one weight-1 question and the prose carries the nuance the state cannot.
# `$v` is now read as `[...]|first` rather than bound from a streaming path. The old form bound `as $v`
# to an expression that yields ZERO outputs when aws-node has no ENABLE_PREFIX_DELEGATION env var (or no
# aws-node exists at all), which makes the whole jq program emit nothing and trips the helper's
# "produced no output" abort. Every fixture happens to set the variable, so it never fired; a real
# cluster that does not set it would have aborted the pillar. `first` over a list always yields exactly
# one value, null included -- the same idiom sec-4 uses for $mode.
m4 net-3 daemonsets nodes cluster nodeclasses 'input as $n|input as $cl|input as $nc|[$n.items[]?|select((.metadata.labels["eks.amazonaws.com/compute-type"]//"")!="fargate")] as $ec2set|($ec2set|length) as $ec2|([$ec2set[]|select((.metadata.labels["eks.amazonaws.com/compute-type"]//"")=="auto")]|length) as $auto|[$nc.items[]?|select((((.spec.advancedNetworking.ipv4PrefixSize)//"")|tostring)=="32")|.metadata.name] as $off| if (($cl.cluster.computeConfig.enabled==true) and $ec2>0 and $auto==$ec2) then (if ($off|length)>0 then "none~every EC2 node is an EKS Auto Mode node, but NodeClass \($off|join(", ")) sets advancedNetworking.ipv4PrefixSize to 32 (secondary IP mode), which is prefix delegation turned off" else "all~every EC2 node is an EKS Auto Mode node and Auto Mode defaults to prefix delegation (/28 prefixes) for pod networking; no NodeClass sets advancedNetworking.ipv4PrefixSize to 32 (secondary IP mode)" end) elif $ec2==0 then "na~fargate" else (([.items[]?|select(.metadata.name=="aws-node")|.spec.template.spec.containers[]?.env[]?|select(.name=="ENABLE_PREFIX_DELEGATION")|.value]|first) as $v|(if $auto>0 then " (\($auto) of \($ec2) EC2 nodes are EKS Auto Mode nodes and use prefix delegation by default; the remaining \($ec2 - $auto) take their pod IP mode from this aws-node DaemonSet)" else "" end) as $mix| if $v=="true" then "all~prefix delegation on"+$mix else "none~off"+$mix end) end'
# net-4 — RESCOPED. It used to ask whether "separate SGs" are used for control plane and nodes, by
# testing whether resourcesVpcConfig.securityGroupIds contains clusterSecurityGroupId. That premise is
# wrong. AWS: "The cluster security group is applied by default to the Kubernetes control plane managed
# by Amazon EKS as well as any managed compute resources created by Amazon EKS. ADDITIONAL cluster
# security groups control communications from the Kubernetes control plane to compute resources."
# So the cluster SG spans BOTH planes by design and is never a member of the additional list — the
# check reported "separate SGs" on essentially every cluster, describing a separation that does not
# exist. AWS also says the old control-plane/node SG split is "no longer required and can be removed".
# The measurable question that remains is whether the cluster SG's default allow-ALL egress has been
# narrowed — AWS: "Optionally, users can remove this egress rule and limit the open ports between the
# cluster and nodes." `na` when the cluster SG cannot be identified: absent data is not a finding.
# net-4 catches ANY rule that opens every port to the world, not only the literal `IpProtocol: "-1"`
# shape EKS creates by default. A `tcp 0-65535 -> 0.0.0.0/0` rule grants identical egress and used to
# score as "narrowed" -- the same FromPort/ToPort blind spot that was fixed for INGRESS in net-2 and not
# carried across to this egress check when it was written.
m2 net-4 sg cluster 'input as $cl|($cl.cluster.resourcesVpcConfig.clusterSecurityGroupId//"") as $csg|([.SecurityGroups[]?|select(.GroupId==$csg)]|first) as $g| if ($csg|length)==0 then "na~no cluster security group" elif $g==null then "na~cluster SG not in the collected security groups" elif ([$g.IpPermissionsEgress[]?|select(([.IpRanges[]?.CidrIp]|index("0.0.0.0/0")) and (.IpProtocol=="-1" or ((.FromPort//0)<=1 and (.ToPort//0)>=65535)))]|length)>0 then "none~cluster SG \($csg) still allows ALL egress to 0.0.0.0/0 (EKS default)" else "all~cluster SG \($csg) egress is narrowed" end'

# ── workload-security (16) ──
m2 sec-10 validatingwebhooks mutatingwebhooks 'input as $mw| ([(.items[]?,$mw.items[]?)|select((.metadata.name|test("aws-load-balancer|vpc-resource|pod-identity|^eks-|amazon-"))|not)]|length) as $n| if $n>0 then "all~\($n) non-AWS webhooks" else "none~only AWS-installed webhooks" end'
# sec-11 reads the enforce LEVEL, not merely the presence of a `pod-security.kubernetes.io/` label.
# Matching the key prefix alone meant `pod-security.kubernetes.io/enforce: privileged` -- which opts the
# namespace OUT of restriction -- scored `all` on a High-severity control. Only `restricted` and
# `baseline` are enforcement; `privileged` is the absence of it. `warn`/`audit` labels do not gate
# admission at all, so only the `enforce` key counts.
m2 sec-11 namespaces pods 'input as $p|[.items[]|select(.metadata.name|test("^(kube-|amazon-)")|not)] as $ns|($ns|length) as $t|([$ns[]|select((.metadata.labels//{})|to_entries|any((.key|test("^pod-security.kubernetes.io/enforce$")) and (.value=="restricted" or .value=="baseline")))]|length) as $ok| if $t==0 then "na~no workload namespaces" else b($ok;$t)+"~\($ok)/\($t) ns enforce restricted|baseline" end'
# sec-16 same correction as adm-1: an installed engine with only templates, or only Audit-mode policies,
# is not enforcing anything.
m3 sec-16 kyverno constraints constrainttemplates 'input as $c|input as $ct|(([.items[]?|select((.spec.validationFailureAction//""|ascii_downcase)=="enforce")]|length)+([$c.items[]?]|length)) as $n|([$ct.items[]?]|length) as $tmpl| if $n>0 then "all~policy engine enforcing \($n) policy/ies" elif $tmpl>0 then "some~policy engine installed but only ConstraintTemplates (schemas), no enforcing policy" else "none~none" end'
# adm-1 counts what is ENFORCED. A Gatekeeper ConstraintTemplate is a schema: without a Constraint
# object instantiating it, Gatekeeper enforces nothing. Counting templates meant 5 templates and zero
# Constraints scored `all~5 policies` while the cluster enforced none -- and adm-2/adm-3 already read
# `constraints.json` correctly, so this was an internal inconsistency. Kyverno policies count only in
# Enforce mode; Audit-mode policies report but do not block.
m3 adm-1 kyverno constraints constrainttemplates 'input as $c|input as $ct|([.items[]?|select((.spec.validationFailureAction//""|ascii_downcase)=="enforce")]|length) as $kyv|([$c.items[]?]|length) as $gk|($kyv+$gk) as $n|([$ct.items[]?]|length) as $tmpl| if $n>=5 then "all~\($n) enforcing policies" elif $n>0 then "some~\($n) enforcing policies" elif $tmpl>0 then "none~\($tmpl) Gatekeeper ConstraintTemplate(s) but no Constraint objects, so nothing is enforced" else "none~0" end'
# adm-2 judges what a policy DOES, not what it is called. It used to accept a case-insensitive substring
# match on "privileg" against the policy kind/name, so a policy named `allow-privileged-for-ci` -- an
# exception that PERMITS privileged pods -- scored as blocking them. Now: a Kyverno policy counts only if
# it is in Enforce mode AND its rule pattern requires privileged==false; Gatekeeper counts real
# Constraint objects (see adm-1), not templates.
m2 adm-2 kyverno constraints 'input as $c|([.items[]?|select((.spec.validationFailureAction//""|ascii_downcase)=="enforce")]) as $kyv|([$c.items[]?]) as $gk|(($kyv|length)+($gk|length)) as $t|([$kyv[]|select([.spec.rules[]?.validate.pattern.spec.containers[]?.securityContext.privileged?]|any(.==false))]|length) as $kok| if $t==0 then "none~no enforcing admission policy" elif ($kok+($gk|length))>0 then "all~\($kok+($gk|length)) enforcing policy/ies restrict privileged" else "some~\($t) enforcing policy/ies, none demonstrably restricting privileged" end'
m2 adm-3 kyverno constraints 'input as $gk|([.items[]?|(.spec.validationFailureAction // (.spec.rules[]?.validate.failureAction) // empty)] + [$gk.items[]?|(.spec.enforcementAction // empty)]) as $a| if ($a|length)==0 then (if (([.items[]?]|length)+([$gk.items[]?]|length))==0 then "na~no policy engine installed" else "some~policies present but no enforcement action set (defaults to audit)" end) elif ([$a[]|select(test("^(Enforce|enforce|deny)$"))]|length)>0 then "all~enforce" else "some~audit" end'
m sec-12 pods '[.items[]|select((.metadata.namespace//"")|test("^(kube-|amazon-)")|not)|.spec.containers[]?] as $c|($c|length) as $t|([$c[]|select((.image|test(":latest$")) or ((.image|test("@sha256:|:[^/]+$"))|not))]|length) as $bad| if $t==0 then "na~no workload containers" else b(($t-$bad);$t)+"~\(($t-$bad))/\($t) pinned image tags" end'
m sec-15 pods '[.items[]|select((.metadata.namespace//"")|test("^(kube-|amazon-)")|not)|.spec.securityContext as $ps|.spec.containers[]?|{sc:.securityContext,ps:$ps}] as $c|($c|length) as $t|([$c[]|select(.sc.runAsNonRoot==true or .sc.readOnlyRootFilesystem==true or .sc.allowPrivilegeEscalation==false or .ps.runAsNonRoot==true)]|length) as $ok| b($ok;$t)+"~\($ok)/\($t) secctx (workloads)"'
# WINDOWS SCOPE — podsec-5 excludes Windows pods, podsec-1 does NOT. The asymmetry is deliberate and
# it is not about Linux-vs-Windows in general: it is about whether Kubernetes will accept the field on
# a Windows pod at all.
#   podsec-5 (`capabilities.drop: [ALL]`) EXCLUDES Windows. `securityContext.capabilities` is
#     REJECTED BY THE API SERVER on a pod that declares `spec.os.name: windows` — validateWindows in
#     pkg/apis/core/validation/validation.go returns Forbidden, "cannot be set for a windows pod" —
#     and the Pod Security Standards list Linux Capabilities as one of the three controls it relaxes
#     for Windows pods (with Privilege Escalation and Seccomp). The field is unsettable there, so
#     counting a Windows container as one that failed to set it reports a fact about Kubernetes as a
#     finding about the cluster. The nodeSelector signal is kept alongside `spec.os.name` because a
#     dropped capability is inert on a Windows node whether or not the pod declares its OS.
#   podsec-1 (`runAsNonRoot`) DOES NOT EXCLUDE Windows, because all three things that would justify
#     an exclusion are false:
#     * ADMISSIBLE — `runAsNonRoot` is absent from validateWindows's forbidden list, so the API
#       server accepts it on a Windows pod. (`runAsUser`/`runAsGroup` are the ones it rejects.)
#     * REQUIRED BY PSS-RESTRICTED — PSS relaxes only Privilege Escalation, Seccomp and Linux
#       Capabilities for `spec.os.name: windows`. Those three checks each carry a Windows branch;
#       check_runAsNonRoot.go has none, so Restricted demands `runAsNonRoot` on Windows pods too.
#     * ENFORCED BY THE KUBELET — pkg/kubelet/kuberuntime/security_context_windows.go carries a
#       Windows-specific verifyRunAsNonRoot with `windowsRootUserName = "ContainerAdministrator"`,
#       unchanged from release-1.24 through master. The Kubernetes Windows documentation says the
#       same: "securityContext.runAsNonRoot — this setting will prevent containers from running as
#       ContainerAdministrator which is the closest equivalent to a root user on Windows", and names
#       it as one of only TWO pod-level securityContext fields that work on Windows.
#     DO NOT RE-ADD A WINDOWS EXCLUSION HERE. It made a Windows pod running as ContainerAdministrator
#     with no `runAsNonRoot` score `all` on a mixed cluster, and on a Windows-only cluster it made the
#     question `na` — which SKILL.md excludes from numerator AND denominator, so a High-severity
#     control left the Security score entirely. That is exactly the implied pass SKILL.md's "Windows
#     node pools are genuine gaps, not implied passes" forbids, and sec-15 above already counts the
#     same Windows container and fails it, so the exclusion also made this file disagree with itself.
#   `runAsNonRoot` is NECESSARY BUT NOT SUFFICIENT on Windows: the kubelet check passes vacuously on
#     an image with no USER directive, so podsec-1 also fails a container whose EFFECTIVE
#     `windowsOptions.runAsUserName` (container overriding pod) is ContainerAdministrator even when
#     `runAsNonRoot: true` is set. Compared case-insensitively, matching the kubelet's
#     strings.EqualFold. On Linux pods the field is absent, so the clause is inert there.
# podsec-2 (privileged) and podsec-4 (added capabilities) are not excluded either: a Windows container
# legitimately passes both, since it has neither privileged mode nor capabilities to add.
m podsec-1 pods '[.items[]|select((.metadata.namespace//"")|test("^(kube-|amazon-)")|not)|.spec.securityContext as $ps|.spec.containers[]?|{sc:.securityContext,ps:$ps}] as $c|($c|length) as $t|([$c[]|select((.sc.runAsNonRoot==true or .ps.runAsNonRoot==true) and ((((.sc.windowsOptions.runAsUserName // .ps.windowsOptions.runAsUserName) // "")|ascii_downcase)!="containeradministrator"))]|length) as $ok| b($ok;$t)+"~\($ok)/\($t) nonroot (workloads)"'
m podsec-2 pods '[.items[]|select((.metadata.namespace//"")|test("^(kube-|amazon-)")|not)|.spec.containers[]?] as $c|($c|length) as $t|([$c[]|select((.securityContext.privileged//false)!=true)]|length) as $ok| b($ok;$t)+"~\($ok)/\($t) nonpriv (workloads)"'
m podsec-3 pods '[.items[]|select((.metadata.namespace//"")|test("^(kube-|amazon-)")|not)] as $p|($p|length) as $t|([$p[]|select([.spec.volumes[]?|select(.hostPath)]|length==0)]|length) as $ok| b($ok;$t)+"~\($ok)/\($t) no hostPath (workloads)"'
m podsec-4 pods '[.items[]|select((.metadata.namespace//"")|test("^(kube-|amazon-)")|not)|.spec.containers[]?|select(.securityContext.capabilities.add)] as $c|($c|length) as $t|([$c[]|select(([.securityContext.capabilities.add[]?]|any(.=="NET_ADMIN" or .=="SYS_ADMIN" or .=="ALL"))|not)]|length) as $ok| if $t==0 then "na~no container adds capabilities" else b($ok;$t)+"~\($ok)/\($t) safe caps (declared adds)" end'
m podsec-5 pods '[.items[]|select((.metadata.namespace//"")|test("^(kube-|amazon-)")|not)] as $wl|([$wl[]|select(((.spec.os.name//"")=="windows") or (((.spec.nodeSelector//{})["kubernetes.io/os"]//"")=="windows"))]|length) as $win|[$wl[]|select((((.spec.os.name//"")=="windows") or (((.spec.nodeSelector//{})["kubernetes.io/os"]//"")=="windows"))|not)|.spec.containers[]?] as $c|($c|length) as $t|([$c[]|select([.securityContext.capabilities.drop[]?]|any(.=="ALL"))]|length) as $ok| if $t==0 then "na~no Linux workload containers" else b($ok;$t)+"~\($ok)/\($t) drop ALL (workloads)"+(if $win>0 then " (\($win) Windows pod(s) excluded — securityContext.capabilities is rejected by the API server on a Windows pod, so drop ALL cannot be set there)" else "" end) end'
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

**Remediation:** The cluster security group does **not** affect the public endpoint — AWS is explicit
that "the cluster security group doesn't affect the public endpoint", so restricting it there changes
nothing. The control is `publicAccessCidrs`:

```bash
aws eks update-cluster-config --name <CLUSTER> --region <REGION> \
  --resources-vpc-config endpointPublicAccess=true,publicAccessCidrs="1.2.3.4/32",endpointPrivateAccess=true
```

Better still, disable public access entirely (`endpointPublicAccess=false`) and reach the API over the
private endpoint. If you do restrict `publicAccessCidrs`, either enable private access or include the
nodes' egress IPs — otherwise nodes cannot reach the API server and will fail to join. Cluster security
groups are the control for the **private** endpoint, not the public one.

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

<!-- MAINTAINER NOTE — not report content. Found while verifying render output for the rbac-1 fix
     above: this file's renderer (question_prose()/md_inline() in assets/render-report.py) only
     recognizes a bullet as ONE physical line — a continuation line wrapped onto the next line (no
     leading `-`/`*`) breaks out of the `<ul>` as loose sibling text, dropping the rest of the bullet
     into the report with the wrong markup. These two bullets were wrapped across three lines each and
     rendered broken; reflowed onto one line per bullet, content unchanged. Verified 2026-09-11 by
     calling question_prose()+md_inline() directly against this file. -->

**Remediation:**
- **Preferred — Pod Identity.** Install the `eks-pod-identity-agent` add-on, then `aws eks create-pod-identity-association --cluster-name <name> --namespace <ns> --service-account <sa> --role-arn <arn>`. The role's trust policy names `pods.eks.amazonaws.com`; no per-cluster OIDC edit is needed.
- **IRSA.** `eksctl create iamserviceaccount --cluster <name> --name <sa> --namespace <ns> --attach-policy-arn <arn>` (this also creates the IAM OIDC provider if it is missing). Verify with `aws iam list-open-id-connect-providers`.

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

<!-- MAINTAINER NOTE — not report content. Deliberately placed outside the blockquote and the
     Remediation block so the renderer does not extract it. History: the scorer (this file's scorer
     block, `m2 rbac-1`) was extended to also read awsauth.json — an IAM principal mapped into
     system:masters via aws-auth is a full-cluster-admin path no ClusterRoleBinding check can see, and
     the scorer's own comment documents why. This remediation previously covered only the
     ClusterRoleBinding path, told the reader to "remove non-system bindings" with no check that the
     binding being removed wasn't the operator's own or a break-glass account's only route to
     cluster-admin, and no rollback. Now covers both paths the question can fail on, warns and verifies
     before any removal, and gives the exact re-creation command for the ClusterRoleBinding case.
     Verified 2026-09-11 against docs.aws.amazon.com/eks/latest/userguide (authenticationMode: CONFIG_MAP
     vs API vs API_AND_CONFIG_MAP) and the AWS CLI reference for update-access-entry /
     disassociate-access-policy / delete-access-entry. -->

> Non-system cluster-admin grants provide excessive cluster-wide access — whether granted through a
> Kubernetes `ClusterRoleBinding` or through an IAM principal mapped into the `system:masters` group.
> Both paths reach the same place: unrestricted cluster-admin.

**Commands:**
```bash
kubectl get clusterrolebindings -o json
# Filter roleRef.name == "cluster-admin", check subjects
kubectl get configmap aws-auth -n kube-system -o json
# Check data.mapRoles / data.mapUsers for "system:masters"
```

**Remediation:** Before you remove anything: **confirm you have another way in.** A cluster-admin
binding or mapping that looks like "the" non-system grant this finding names may be the operator's own
only path to cluster-admin, or a break-glass account's. Removing it strands you on a cluster whose
entire point is that you administer it. From the identity that will remain after the change (not the
one you are about to remove), confirm it actually has cluster-admin:

```bash
kubectl auth can-i --list --as=<remaining-identity-or-serviceaccount>
# or, for an IAM principal not yet mapped to a Kubernetes username:
kubectl auth can-i '*' '*' --as=<kubernetes-username-or-group-that-will-remain>
```

Only remove the binding or mapping once that comes back with full access.

**Path 1 — a non-system `ClusterRoleBinding` bound to `cluster-admin`:**

```bash
# Save it first — this is also the rollback if the removal turns out to be wrong:
kubectl get clusterrolebinding <BINDING_NAME> -o yaml > <BINDING_NAME>-backup.yaml
kubectl delete clusterrolebinding <BINDING_NAME>
```

Rollback, if needed:
```bash
kubectl apply -f <BINDING_NAME>-backup.yaml
```

**Path 2 — an IAM principal mapped into `system:masters`:** this path is materially more dangerous
than path 1: a `ClusterRoleBinding` mistake strands one subject, but a bad edit to the cluster's
identity mapping can lock out **every** IAM principal at once, including the one making the edit.
Which mechanism applies, and how to tell:

```bash
aws eks describe-cluster --name <CLUSTER> --region <REGION> --query 'cluster.accessConfig.authenticationMode'
```

**If `CONFIG_MAP`, or `API_AND_CONFIG_MAP` with the mapping found in `data.mapRoles`/`data.mapUsers`:**
the aws-auth ConfigMap governs this principal. Back it up, then edit only that principal's entry — never
delete the ConfigMap itself, which also carries the node-bootstrap role mappings
(`system:bootstrappers`/`system:nodes`) and would stop new nodes from joining as well as removing
cluster-admin:

```bash
kubectl get configmap aws-auth -n kube-system -o yaml > aws-auth-backup.yaml
kubectl edit configmap aws-auth -n kube-system
```

In the editor, remove only the offending role/user entry, or drop `system:masters` from its groups
list — leave every other entry untouched (deleting the whole ConfigMap breaks node bootstrapping too).
Rollback, if needed: `kubectl apply -f aws-auth-backup.yaml`.

**If `API`, or `API_AND_CONFIG_MAP` with the mapping found via an access entry:** this cluster uses EKS
access entries instead; the aws-auth ConfigMap is either ignored (`API`) or only a fallback for
principals with no access entry (`API_AND_CONFIG_MAP`). Find and narrow the entry rather than editing a
ConfigMap that may not even be consulted:

```bash
aws eks list-access-entries --cluster-name <CLUSTER> --region <REGION>
aws eks describe-access-entry --cluster-name <CLUSTER> --region <REGION> --principal-arn <ARN>
aws eks list-associated-access-policies --cluster-name <CLUSTER> --region <REGION> --principal-arn <ARN>
```

If admin comes from `kubernetesGroups: ["system:masters", ...]` on the entry, replace the list with the
remaining groups (an empty list removes group-based access without touching any associated policy):

```bash
aws eks update-access-entry --cluster-name <CLUSTER> --region <REGION> --principal-arn <ARN> --kubernetes-groups <REMAINING_GROUPS_SPACE_SEPARATED>
```

If admin comes from an associated policy (`AmazonEKSClusterAdminPolicy` with `accessScope.type=cluster`),
remove only that policy — this leaves the access entry and any other associated policy intact, unlike
`delete-access-entry`, which removes the principal's access entirely:

```bash
aws eks disassociate-access-policy --cluster-name <CLUSTER> --region <REGION> --principal-arn <ARN> --policy-arn arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy
```

Rollback, if needed: re-run `update-access-entry` with `system:masters` restored, or associate the
policy again:

```bash
aws eks associate-access-policy --cluster-name <CLUSTER> --region <REGION> --principal-arn <ARN> --policy-arn arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy --access-scope type=cluster
```

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
