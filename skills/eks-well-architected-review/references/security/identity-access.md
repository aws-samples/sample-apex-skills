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
> `measured`, the SCORER IS AUTHORITATIVE — answer it from the collected data.
> Use the prose for rationale and remediation wording only.
> (This file holds the scorer for the ENTIRE Security pillar, including the questions documented in
> data-protection.md, network.md, workload-security.md and governance-compliance.md.)

---

## Table of Contents

1. [Security pillar scorer — run by `assets/score.sh`, not by hand (covers all 57 Security questions)](#security-pillar-scorer--run-by-assetsscoresh-not-by-hand-covers-all-57-security-questions)
2. [Implement a strong identity foundation](#implement-a-strong-identity-foundation)
   - [sec-1: Is the EKS cluster API server endpoint configured with private access enabled?](#sec-1-is-the-eks-cluster-api-server-endpoint-configured-with-private-access-enabled)
   - [sec-2: Is public API server access restricted to specific CIDR ranges rather than reachable from the whole internet?](#sec-2-is-public-api-server-access-restricted-to-specific-cidr-ranges-rather-than-reachable-from-the-whole-internet)
   - [sec-3: Do you allow users to assume an IAM Role and map that role to a Kubernetes RBAC group, rather than creating individual user mappings in the aws-auth ConfigMap?](#sec-3-do-you-allow-users-to-assume-an-iam-role-and-map-that-role-to-a-kubernetes-rbac-group-rather-than-creating-individual-user-mappings-in-the-aws-auth-configmap)
   - [sec-5: Do you use a dedicated IAM role to create EKS clusters that is not used for routine cluster operations or day-to-day management tasks?](#sec-5-do-you-use-a-dedicated-iam-role-to-create-eks-clusters-that-is-not-used-for-routine-cluster-operations-or-day-to-day-management-tasks)
   - [sec-6: Is pod-level workload identity (EKS Pod Identity or IRSA) configured for workloads that need AWS access?](#sec-6-is-pod-level-workload-identity-eks-pod-identity-or-irsa-configured-for-workloads-that-need-aws-access)
   - [sec-7: Do you restrict access to the kube-system namespace to super administrators only, preventing regular users from modifying critical cluster components?](#sec-7-do-you-restrict-access-to-the-kube-system-namespace-to-super-administrators-only-preventing-regular-users-from-modifying-critical-cluster-components)
   - [sec-9: Do non-system ClusterRoles avoid wildcard (star) resource and verb permissions?](#sec-9-do-non-system-clusterroles-avoid-wildcard-star-resource-and-verb-permissions)
3. [Automate security best practices](#automate-security-best-practices)
   - [sec-17: Is cluster access granted through EKS access entries (API authentication mode) rather than the legacy aws-auth ConfigMap?](#sec-17-is-cluster-access-granted-through-eks-access-entries-api-authentication-mode-rather-than-the-legacy-aws-auth-configmap)
   - [sec-18: Is an OIDC provider configured for the EKS cluster to enable IRSA?](#sec-18-is-an-oidc-provider-configured-for-the-eks-cluster-to-enable-irsa)
4. [RBAC Configuration](#rbac-configuration)
   - [rbac-1: Is cluster-admin restricted to the two built-in subjects expected to hold it?](#rbac-1-is-cluster-admin-restricted-to-the-two-built-in-subjects-expected-to-hold-it)
   - [rbac-2: Do service accounts use namespace-scoped permissions (not cluster-wide)?](#rbac-2-do-service-accounts-use-namespace-scoped-permissions-not-cluster-wide)
   - [rbac-3: Are role bindings free of stale references to non-existent subjects?](#rbac-3-are-role-bindings-free-of-stale-references-to-non-existent-subjects)
   - [rbac-4: Do default service accounts in non-system namespaces have automountServiceAccountToken disabled?](#rbac-4-do-default-service-accounts-in-non-system-namespaces-have-automountserviceaccounttoken-disabled)

---

## Security pillar scorer — run by `assets/score.sh`, not by hand (covers all 57 Security questions)

This single block scores the **entire Security pillar** (this file + data-protection, network,
workload-security, governance-compliance). `${CLAUDE_SKILL_DIR}/assets/score.sh security "$WORK"` extracts
this block and runs it. Do not paste it into a shell: it defines shell functions (`emit`, `rl`, `g`, `m`…) and
calls them once per question, and a Bash permission rule matches literal command text — so no rule can
match a function name and every call prompts, or fails outright under a no-prompt policy. It requires
`$WORK` (set in SKILL.md Step 2) populated with the canonical JSON files, and appends one JSONL line per
question to `$WORK/results.jsonl`.

Every line carries `pillar`, `id`, `track`, `state` and `detail` — the shape SKILL.md Step 5 documents —
and, for the questions whose scorer runs an `rl` line, a **sixth `resources` key naming the objects the
check counted**, so the report can print `payments/api` instead of `7/9` without re-implementing the
detection in Python. `resources` is evidence, never verdict: it is built by a separate `jq` call that
cannot abort the question, so a broken name expression costs the list and nothing else. Three states are
distinguishable and the report says which: **no key** (this question publishes no list), **`null`** (the
list could not be built), **empty arrays** (the check looked and found nothing).

The `m`/`m2`/`m3`/`m4`/`m6`/`m7` thresholds are the determinism guarantee and are not yours to edit.

Run it as-is. Governance questions emit `state:"unknown"` (reported as Not Assessed). Do not hand-edit
a `g` call.

```bash
W="$WORK"
B='def b($ok;$t): if $t==0 then "na" elif ($ok*100/$t)>=90 then "all" elif ($ok*100/$t)>=70 then "most" elif $ok>0 then "some" else "none" end; def ishy: ((.spec.providerID? // "")|tostring) as $p | if ($p|test("^eks-hybrid:")) then true elif ($p|test("^aws:")) then false else ((.metadata.labels["eks.amazonaws.com/compute-type"]//"")=="hybrid") end; def isec2: ((.metadata.labels["eks.amazonaws.com/compute-type"]//"")!="fargate") and (ishy|not); def hyx($h): if $h>0 then " (\($h) EKS Hybrid Node(s) excluded: they run on infrastructure outside AWS and this question does not judge them)" else "" end; def hyna($h;$why): "na~no EC2 nodes — this cluster runs \($h) EKS Hybrid Node(s), which run on infrastructure outside AWS: \($why)"; def iswin: ((.metadata.labels["kubernetes.io/os"] // .status.nodeInfo.operatingSystem // "")|tostring)=="windows"; def islinux: isec2 and (iswin|not); def iswinspec: ((.os.name // "")=="windows") or ((.nodeSelector["kubernetes.io/os"] // "")=="windows") or ((.nodeSelector["beta.kubernetes.io/os"] // "")=="windows") or (.nodeSelector["node.kubernetes.io/windows-build"] != null) or (((.affinity.nodeAffinity.requiredDuringSchedulingIgnoredDuringExecution.nodeSelectorTerms)//[]) as $ts|(($ts|length)>0) and ($ts|any(.[]; any(.matchExpressions[]?; (.key//"") as $k|(.operator//"") as $o|(.values//[]) as $v|(((($k=="kubernetes.io/os") or ($k=="beta.kubernetes.io/os")) and ((($o=="In") and ($v|any(.[]; .=="windows")) and ($v|all(.[]; . != "linux"))) or (($o=="NotIn") and ($v|any(.[]; .=="linux")) and ($v|all(.[]; . != "windows"))))) or (($k=="node.kubernetes.io/windows-build") and ((($o=="In") and (($v|length)>0)) or ($o=="Exists"))))))) and ($ts|all(.[]; ((((.matchExpressions//[])|length)==0) and (((.matchFields//[])|length)==0)) or any(.matchExpressions[]?; (.key//"") as $k|(.operator//"") as $o|(.values//[]) as $v|(((($k=="kubernetes.io/os") or ($k=="beta.kubernetes.io/os")) and ((($o=="In") and ($v|all(.[]; . != "linux"))) or (($o=="NotIn") and ($v|any(.[]; .=="linux"))) or ($o=="DoesNotExist"))) or (($k=="node.kubernetes.io/windows-build") and (($o=="In") or ($o=="Exists")))))))); def winds: [.items[]?|select((.spec.template.spec//{})|iswinspec)|{key:((.metadata.namespace//"")+"/"+(.metadata.name//"")),value:true}]|from_entries; def iswinpod($w): (.spec|iswinspec) or ((.metadata.namespace//"") as $ns|any(.metadata.ownerReferences[]?; ((.kind//"")=="DaemonSet") and ($w[$ns+"/"+(.name//"")]//false))); def winx($w): if $w>0 then " (\($w) Windows node(s) not assessed — this skill supports Linux nodes only)" else "" end; def winpx($w): if $w>0 then " (\($w) Windows pod(s) not assessed — this skill supports Linux nodes only)" else "" end; def winna($w): "na~NOT ASSESSED — the only nodes this question would judge are \($w) Windows node(s); this skill supports Linux nodes only"; def winpna($w): "na~NOT ASSESSED — the only pods this question would judge are \($w) Windows pod(s); this skill supports Linux nodes only";'
# Policy-engine helpers, defined ONCE in $PE and prepended like $B. Only adm-2 calls into them (kypriv ->
# kyact, kycw, selblank, kypat, unanchor, privfalse; kynsov and kyver18 for its caveats). gkenf is called by
# nothing but stays: it is the Gatekeeper half of a pair with kyenf, and reduce.sh and render-report.py name it
# as the example prelude definition.
# NONE OF THE FOUR POLICY-ENGINE QUESTIONS PUBLISHES AN ENFORCE-vs-AUDIT COUNT. They score on whether the
# collected policy files carry anything; "N policies refuse at admission" would assert an outcome the
# collection cannot establish (a mutate-only policy at spec-level Enforce would count as refusing, and so
# would a validate rule with `failureAction: Audit` beside a mutate-only sibling). Do not add one. adm-2's
# privileged disclosure is a claim about a policy BODY that was read, not about the API server.
# $PE is a second variable because reduce.sh requires exactly one distinct `^B='` value across all reference
# files; a Gatekeeper predicate inside $B would enter every pillar's state<->ratio gate.
#
# gkenf  Gatekeeper Constraint refuses at admission. `spec.enforcementAction: deny` (default when absent)
#        does; `dryrun` and `warn` do not. `scoped` counts an entry only when its `action` is `deny` AND its
#        `enforcementPoints` names an ADMISSION point: `validation.gatekeeper.sh`, `vap.k8s.io` or `*` (the
#        `IN(...)` list). Points are constants in Gatekeeper `pkg/util/enforcement_action.go`, matched by
#        `ep.Name == enforcementPoint || ep.Name == AllEnforcementPoints`; `audit.gatekeeper.sh` and the Gator
#        point are not admission, and a new upstream point reads as non-admission (under-reports). An entry
#        with NO `enforcementPoints` does not count: there is no implicit wildcard.
#        CASE-SENSITIVE ON PURPOSE: `GetEnforcementAction` maps anything but literal deny/dryrun/warn/scoped to
#        Unrecognized, so "DENY" or "Validation.Gatekeeper.SH" enforce nothing; lower-casing would over-report.
#        `enforcementAction: ""` IS REACHABLE AND `false` IS CORRECT FOR IT. Do not "fix" it to Deny: that is a
#        false PASS. The CRD Default fires on absence or explicit null, not on "", so "" is stored;
#        `pkg/webhook/policy.go` calls `ValidateEnforcementAction("")`, hits `default:` and errors, and the call
#        site `continue`s past the violation, so the request is ADMITTED. The ""->Deny mapping lives in
#        `constraint_controller.go`, which is why `status.Enforced` can read true anyway.
#        Malformed shapes (non-object entry, scalar `enforcementPoints`, wrong-cased name/action, empty action)
#        report LESS enforcement. `enforcementAction: false` and a scalar `.spec` (neither producible by the API
#        server) reach `true` via the `// "deny"` and `//{}` defaults. `null` reaching `true` is correct (schema
#        default): do not add a `has("enforcementAction")` guard, it breaks the null case.
#        `|objects|` on the action entries and points is load-bearing: `scopedEnforcementActions: ["deny"]`
#        would otherwise abort the pillar with `Cannot index string with string "action"`.
# kyenf  Kyverno policy is in enforce mode, resolved PER RULE and OVERRIDE-FIRST. Rungs, in order:
#          1. the rule's `validate.failureActionOverrides`   2. the rule's `validate.failureAction`
#          3. the policy's `spec.validationFailureActionOverrides` (deprecated, still in the field)
#          4. the policy's `spec.validationFailureAction`
#        Reading only the spec field is a false PASS: `Enforce` with an override `[{action: Audit,
#        namespaces: ["*"]}]` refuses nothing and needs no flag to produce (`Audit` is a legal override value).
#        VERSIONS: `GetValidationFailureAction` is first-rule-wins on every version. From 1.19 `BlockRequest`
#        calls the per-rule `HasEnforcedFailure()` (fb060698e80c); the CLI and policy reports still call
#        `GetValidationFailureAction`, so a report can disagree with this verdict without being wrong. Below
#        v1.13.0 there are no rule-level fields. Two pre-1.19 rungs are 1.18-only: 8891c6c3408c (an
#        override naming neither `namespaces` nor `namespaceSelector` matches ALL namespaces; 1.13-1.17 skip it)
#        and 18349a646d24 (verifyImages resolution scans every entry, not `VerifyImages[0]`). `ky118`
#        models 1.18, `ky117` the earlier ladder, and `kyver18` fires when the published verdict disagrees with
#        EITHER. No version is read from the collected objects. The pre-1.19 ladder has FOUR rungs before the
#        spec field (per rule: overrides, `failureAction`, a `verifyImages` entry; then, after the rule loop,
#        `spec.validationFailureActionOverrides`); omitting the last flags the common blanket-Enforce-override
#        form with a divergence that does not exist.
#        `pkg/policycache/cache.go checkValidationFailureActionOverrides` is a second resolver that differs from
#        the engine; the engine path is modelled because it decides admission. Not modelled: on a rule-name
#        lookup miss `failureActionForRule` defers to `GetValidationFailureAction()`.
#        CLUSTER-WIDE OVERRIDE = no `namespaceSelector` and `namespaces` absent/null or containing `*`.
#        `matchOverride` reads `if v.Namespaces == nil { if v.NamespaceSelector == nil { return v.Action, true`.
#        Omitting the absent case is a false PASS (and kynsov would mislabel it namespace-scoped). It is
#        `.namespaces==null`, not a length test: `namespaces: []` matches nothing upstream.
#        AN EMPTY SELECTOR IS A BLANKET OVERRIDE, not residue: `LabelSelectorAsSelector` (kubernetes/apimachinery
#        pkg/apis/meta/v1/helpers.go) returns `labels.Nothing()` for nil and `labels.Everything()` when
#        MatchLabels and MatchExpressions are both empty, via `matchOverride` -> `utils.CheckSelector`. `selblank`
#        tests nil and `{"matchLabels":{},"matchExpressions":[]}` (what a chart emits for an unset key). A selector
#        with labels, or specific `namespaces`, is unresolvable residue: the field decides and `kynsov` counts
#        such policies so adm-2 says the split does not cover them. `namespaces: []` is also counted (over-discloses).
#        KNOWN DIVERGENCES, BOTH UNDER-REPORTING: `kycw` keeps an override whose `action` is outside the enum
#        (upstream `IsValid()` skips it), and `kyact` takes the validate branch for an EMPTY `validate: {}`
#        where upstream `HasValidate()` needs it non-empty.
#        `kycw` uses null as a sentinel (`.action//empty]|first`): an entry with no `action` reads as no
#        override, matching upstream (`matchOverride` starts with `if !v.Action.IsValid() { continue }`).
#        `.action//empty` drops only null/false/absent, so `""` or `Nonsense` is kept and read as "does not say
#        Enforce": an under-report chosen over fidelity, which would turn an invalid action into a false PASS.
#        `kyact` FACTORS THE LADDER AND adm-2 GATES ITS PATTERN SCAN ON IT: scanning the whole policy would let
#        `kyenf` and the privileged pattern be satisfied by DIFFERENT rules (rule `a` Enforce with an unrelated
#        pattern, rule `b` Audit carrying `privileged: false`). `kypriv` needs ONE rule to do both.
#        `unanchor` strips a leading Kyverno anchor from every key with `walk`: kyverno/policies
#        `pod-security/baseline/disallow-privileged-containers` writes ANCHORED keys and the STRING "false"
#        (`containers: [ { =(securityContext): { =(privileged): "false" } } ]`). The set mirrors
#        `pkg/engine/anchor/anchor.go`, `^(?P<modifier>[+<=X^])?\((?P<key>.+)\)$`: `()`, `<()`, `X()`, `+()`,
#        `=()`, `^()`. `!()` is NOT an anchor; do not widen. Keys are trimmed first (upstream `TrimSpace`s).
#        The comparison lower-cases `tostring` and accepts `false` (string or boolean) or `!true`; the search
#        covers Pod `spec`, `spec.template.spec` and `spec.jobTemplate.spec.template.spec`.
#        TWO NARROWINGS MUST NOT BE "FIXED" BY WIDENING: only `.containers` is read (NOT `initContainers` or
#        `ephemeralContainers`: a pattern on those still admits a privileged main container), and `anyPattern`
#        is never read BESIDE `pattern` (upstream `validatePatterns` returns inside `if v.pattern != nil`);
#        `anyPattern` is read only when `pattern` is absent/null, and then EVERY alternative must restrict
#        privileged. `validate.deny` and `validate.cel` are unread; adm-2's $P>0 arm says so.
#        SPELLINGS: `Enforce` and legacy `enforce` (upstream `enforceOld`) at spec level and for an override
#        `action`. The rule-level enum is `Audit;Enforce` only, so accepting `enforce` there is one spelling
#        wider than upstream. Not `ascii_downcase`: `ENFORCE` is in no enum. gkenf accepts one spelling because
#        Gatekeeper does; do not "tidy" the two halves into agreement.
#        `failureActionForRule` (pkg/engine/api/engineresponse.go) returns the rule's `validate.failureAction`
#        when set, else `spec.validationFailureAction`; `HasEnforcedFailure` blocks if ANY failed rule resolves to
#        enforce. The fallback is per rule and matters on nearly every policy because
#        `+kubebuilder:default=Audit` populates the spec field. `failureAction: ""` is a SET pointer and
#        suppresses the fallback like `Audit`; hence `($v|has("failureAction")) and ($v.failureAction!=null)`,
#        NOT `//`. A policy with zero rules resolves to not-enforcing.
#        A MUTATE-ONLY RULE INHERITS THE SPEC FIELD, A `verifyImages` RULE DOES NOT; do not generalise to "a rule
#        with no `validate` block". `ruleAction` has `if r.HasValidate() {...} else if r.HasVerifyImages() {...
#        if r.VerifyImages[i].FailureAction != nil {...}}` and `kyact` mirrors both; a mutate-only rule returns
#        `("", false)`, so `failureActionForRule` falls to the spec field.
PE='def gkenf: (((.spec|objects)//{}) as $s|(($s.enforcementAction//"deny")|tostring) as $a|if $a=="deny" then true elif $a=="scoped" then ([$s.scopedEnforcementActions[]?|objects|select([.enforcementPoints[]?|objects|((.name//"")|tostring)]|any(IN("validation.gatekeeper.sh","vap.k8s.io","*")))|.action//empty]|any(tostring=="deny")) else false end);def selblank: (.namespaceSelector|not) or (((.namespaceSelector|type)=="object") and ((((.namespaceSelector.matchLabels//{})|length)+((.namespaceSelector.matchExpressions//[])|length))==0));def kycw($l): [$l[]?|objects|select(selblank and ((.namespaces==null) or ([.namespaces[]?]|any(.=="*"))))|.action//empty]|first;def kynsov: (((.spec|objects)//{}) as $s|[$s.validationFailureActionOverrides[]?,($s.rules[]?|objects|(.validate|objects)//{}|.failureActionOverrides[]?)]|any(objects|((selblank|not) or ((.namespaces!=null) and (([.namespaces[]?]|any(.=="*"))|not)))));def kyact($sov;$sf): ((.validate|objects)//null) as $v|((.verifyImages|if type=="array" then . else null end)) as $vi|if $v!=null then ((kycw($v.failureActionOverrides)) as $rov|if $rov!=null then $rov elif ($v|has("failureAction")) and ($v.failureAction!=null) then $v.failureAction elif $sov!=null then $sov else $sf end) elif $vi!=null then ([$vi[]?|objects|select(has("failureAction") and (.failureAction!=null))|.failureAction]) as $va|(if ($va|any((.=="Enforce") or (.=="enforce"))) then "Enforce" elif ($va|length)>0 then $va[0] elif $sov!=null then $sov else $sf end) elif $sov!=null then $sov else $sf end;def kyenf: (((.spec|objects)//{}) as $s|(kycw($s.validationFailureActionOverrides)) as $sov|($s.validationFailureAction) as $sf|[$s.rules[]?|objects|kyact($sov;$sf)]|any((.=="Enforce") or (.=="enforce")));def unanchor: walk(if type=="object" then with_entries(.key|=((gsub("^\\s+|\\s+$";"")) as $t|if ($t|test("^=\\(.+\\)$")) then ($t|capture("^=\\((?<k>.+)\\)$").k) elif ($t|test("^[+<X^]?\\(.+\\)$")) then ("~selector~"+$t) else . end)) else . end);def privfalse: [(.spec?|objects) as $sp|($sp,($sp.template?|objects|.spec?|objects),($sp.jobTemplate?|objects|.spec?|objects|.template?|objects|.spec?|objects))|objects|.containers?|arrays|.[]|objects|.securityContext?|objects|.privileged?|select(.!=null)]|any((tostring|ascii_downcase) as $x|($x=="false") or ($x=="!true"));def kypat: (((.validate|objects)//{}) as $v|if ($v|has("pattern")) and ($v.pattern!=null) then ((($v.pattern|objects|unanchor|privfalse))//false) else (([$v.anyPattern?|arrays|.[]|(if type=="object" then (unanchor|privfalse) else false end)]) as $ap|(($ap|length)>0) and ($ap|all)) end);def kypriv: (((.spec|objects)//{}) as $s|(kycw($s.validationFailureActionOverrides)) as $sov|($s.validationFailureAction) as $sf|[$s.rules[]?|objects|select(kyact($sov;$sf)|((.=="Enforce") or (.=="enforce")))|select(kypat)]|length>0);def ky118a: (((.validate|objects)//null) as $v|((.verifyImages|if type=="array" then . else null end)) as $vi|first((if $v!=null then (kycw($v.failureActionOverrides)|select(.!=null)) else empty end),(if $v!=null then ($v.failureAction|select(.!=null)) else empty end),(if $vi!=null then ([$vi[]?|objects|select(has("failureAction") and (.failureAction!=null))|.failureAction]) as $va|(if ($va|any((.=="Enforce") or (.=="enforce"))) then "Enforce" elif ($va|length)>0 then $va[0] else empty end) else empty end)));def ky118: (((.spec|objects)//{}) as $s|((first($s.rules[]?|objects|ky118a))//(kycw($s.validationFailureActionOverrides))//$s.validationFailureAction));def kycw117($l): [$l[]?|objects|select(([.namespaces[]?]|any(.=="*")) or (((.namespaceSelector|type)=="object") and ((((.namespaceSelector.matchLabels//{})|length)+((.namespaceSelector.matchExpressions//[])|length))==0)))|.action//empty]|first;def ky117a: (((.validate|objects)//null) as $v|((.verifyImages|if type=="array" then . else null end)) as $vi|first((if $v!=null then (kycw117($v.failureActionOverrides)|select(.!=null)) else empty end),(if $v!=null then ($v.failureAction|select(.!=null)) else empty end),(if $vi!=null then ($vi[0]?|objects|.failureAction|select(.!=null)) else empty end)));def ky117: (((.spec|objects)//{}) as $s|((first($s.rules[]?|objects|ky117a))//(kycw117($s.validationFailureActionOverrides))//$s.validationFailureAction));def kyrules: (((.spec|objects)//{}) as $s|([$s.rules[]?|objects]|length)>0);def kyblocks18: (kyrules and ((ky118|tostring) as $a|(($a=="Enforce") or ($a=="enforce"))));def kyblocks17: (kyrules and ((ky117|tostring) as $a|(($a=="Enforce") or ($a=="enforce"))));def kyver18: (kyenf as $n|(($n!=kyblocks18) or ($n!=kyblocks17)));'
# Shape guard applied by `rl`: the result must be an object with `pass` and `fail` string arrays plus an
# optional `context` string array; anything else is recorded as an `rl` failure. `{pass,fail}` rebuilds the
# object so extra keys cannot be smuggled through.
RQ='|if (type=="object") and ((.pass|type)=="array") and ((.fail|type)=="array") and (((.context//[])|type)=="array") and (([(.pass+.fail+(.context//[]))[]|select(type!="string")]|length)==0) and ((.kind==null) or (.kind=="field") or (.kind=="existence")) and ((.excluded==null) or (((.excluded|type)=="number") and (.excluded>=0) and ((.excluded|floor)==.excluded))) and ((.context_only==null) or ((.context_only|type)=="boolean")) then {pass,fail}+(if (.context|type)=="array" then {context} else {} end)+(if .kind!=null then {kind} else {} end)+(if .excluded!=null then {excluded} else {} end)+(if .context_only==true then {context_only:true} else {} end) else error("rl: the program did not return {pass:[string],fail:[string]} with optional context:[string], kind:field|existence, excluded:integer, context_only:boolean") end'
# BUILD THE RECORD WITH jq, NOT printf. `detail` is raw jq output and several questions interpolate
# cluster-controlled strings into it. With printf a `"` would close the string and forge a duplicate `state`
# key, and a newline would forge whole extra records in OTHER pillars. `--arg` escapes instead.
#   -c   without it `jq -n` pretty-prints, results.jsonl stops being JSONL (reduce.sh refuses it) and
#        score.sh's already-scored refusal breaks, because it greps the literal `"pillar":"security"`.
#   ||   this block runs under `bash` with NO `set -e`. Unguarded, one failing record gives rc=0 with a
#        record missing; guarded, the abort names the question that failed.
# Key order stays pillar,id,track,state,detail (SKILL.md Step 5 documents the bytes); `resources` is a
# sixth key appended only for questions that ran `rl`. `--argjson` can fail on size (the value is ONE argv
# entry, ARG_MAX), so the abort names that as a likely cause; the CONTENT cannot fail, since `rl` admits
# only `false`, `null` or one valid compact document.
# THE ID IS RE-ASSERTED: a stale evidence list from the previous question is dropped rather than attached
# to this one. The emit helper is carried by all five pillar files; if you change one, change all five.
emit(){ local rs=false
  if [ "${RESID:-}" = "$1" ]; then rs="${RES:-null}"; fi
  RES= RESID=
  jq -cn --arg id "$1" --arg tr "$2" --arg st "$3" --arg de "$4" --argjson rs "$rs" \
  '{pillar:"security",id:$id,track:$tr,state:$st,detail:$de}+(if $rs==false then {} else {resources:$rs} end)' >> "$W/results.jsonl" \
  || { printf 'SCORER ABORT [%s]: the record was not emitted -- the jq call failed, the OS refused to start it, or the append to results.jsonl failed; any message jq or the OS printed is above. On a large fleet suspect the evidence list rather than the record: the list reaches jq as ONE --argjson argument, so many thousand names can exceed the OS argument-size limit and execve fails with "Argument list too long" before jq runs.\n' "$1" >&2; exit 1; }; }
# rl <id> <collection-file>... '<jq program>'  -- NAME the objects the next `emit` counted.
# The report must print `payments/api` rather than `7/9`, because a correct count over the wrong set is the
# scoping bug a bare count hides. The list is built here, in jq, next to the verdict, so there is no second
# implementation of the detection (jq's `select(.x)` keeps `{}`, `[]`, `""` and `0`; Python's `bool()`
# rejects all four). `rl` EMITS UNADORNED ARRAYS OF STRINGS; sorting, the "showing 12 of N" truncation and
# labels belong to the renderer. A question without an `rl` line publishes no list.
# `rl` is a separate jq call because one SCORER ABORT costs the WHOLE PILLAR its score, and evidence must
# not be able to do that. So `rl` swallows its own failure, records `resources: null`, and the `m` line
# that follows scores the question as usual. Three states: no `resources` key = no list is published;
# `null` = the list could not be built; `[]` = the check looked and found nothing.
# The selection test appears twice in the file (once in `rl`, once in `m`); the report checks the list's
# counts against the ratio in `detail` and reports a mismatch instead of publishing it. Write `fail` as the
# complement (`$all - $pass`) so the test appears once inside `rl`.
# FAILURE REASON: the jq call's stderr goes to $RLERR (`rl.stderr` in the `.eks-war-scorer.<pillar>.<pid>/`
# directory score.sh made for THIS run, never a fixed name in $W, so a planted entry is not written through)
# and is read back into the message; the query is NOT re-run (a second execution can fail differently).
# jq's words are quoted only when the target is a regular writable file (`[ ! -f ] || [ ! -w ]`).
rl(){ local id="$1"; shift; local fs=(); while [ "$#" -gt 1 ]; do fs+=("$W/$1.json"); shift; done; local r n q e= ef="${RLERR:-/dev/null}"; r=$(jq -c "$B$PE $1 $RQ" "${fs[@]}" 2>"$ef"); q=$?; if [ "$q" = 0 ] && [ -n "$r" ] && n=$(printf '%s' "$r" | wc -l | tr -d ' ') && [ "$n" = 0 ]; then RES="$r" RESID="$id"; else RES=null RESID="$id"; if [ ! -f "$ef" ] || [ ! -w "$ef" ]; then e="jq's stderr could not be captured to $ef, so any OS message is on the line above"; else [ -s "$ef" ] && e=$(tr -s '[:space:]' ' ' < "$ef"); e="${e# }"; e="${e% }"; [ -n "$e" ] && e="; jq said: $e"; if [ "$q" != 0 ]; then e="jq exited $q$e"; elif [ -z "$r" ]; then e="jq exited 0 and produced no output at all$e"; else e="jq exited 0 but produced $((n+1)) results, and an evidence list is exactly one$e"; fi; fi; printf 'RESOURCE LIST SKIPPED [%s]: the evidence list could not be built -- %s. THE VERDICT IS UNAFFECTED -- this is not a finding and not a scoring error; the report will say that this step failed and that there is no list for this question.\n' "$id" "$e" >&2; fi; return 0; }
g(){ emit "$1" governance unknown ""; }
m(){ local id="$1" f="$2" p="$3" r st d; r=$(jq -r "$B$PE $p" "$W/$f.json" 2>&1) || { printf 'SCORER ABORT [%s]: jq failed — a missing or malformed collection file is NOT a finding, and must never be scored as one. jq said: %s\n' "$id" "$r" >&2; exit 1; }; [ -n "$r" ] || { printf 'SCORER ABORT [%s]: jq produced no output\n' "$id" >&2; exit 1; }; st="${r%%~*}"; d="${r#*~}"; [ "$r" = "$st" ]&&d=""; emit "$id" measured "${st:-none}" "$d"; }
m2(){ local id="$1" f1="$2" f2="$3" p="$4" r st d; r=$(jq -r "$B$PE $p" "$W/$f1.json" "$W/$f2.json" 2>&1) || { printf 'SCORER ABORT [%s]: jq failed — a missing or malformed collection file is NOT a finding, and must never be scored as one. jq said: %s\n' "$id" "$r" >&2; exit 1; }; [ -n "$r" ] || { printf 'SCORER ABORT [%s]: jq produced no output\n' "$id" >&2; exit 1; }; st="${r%%~*}"; d="${r#*~}"; [ "$r" = "$st" ]&&d=""; emit "$id" measured "${st:-none}" "$d"; }
# Three inputs: sec-18, net-1, rbac-1, and sec-16/adm-1/adm-2/adm-3 (Kyverno and Gatekeeper policy lists).
# In jq, `input` yields f2 then f3 in order.
m3(){ local id="$1" f1="$2" f2="$3" f3="$4" p="$5" r st d; r=$(jq -r "$B$PE $p" "$W/$f1.json" "$W/$f2.json" "$W/$f3.json" 2>&1) || { printf 'SCORER ABORT [%s]: jq failed — a missing or malformed collection file is NOT a finding, and must never be scored as one. jq said: %s\n' "$id" "$r" >&2; exit 1; }; [ -n "$r" ] || { printf 'SCORER ABORT [%s]: jq produced no output\n' "$id" >&2; exit 1; }; st="${r%%~*}"; d="${r#*~}"; [ "$r" = "$st" ]&&d=""; emit "$id" measured "${st:-none}" "$d"; }
# Four inputs, for `sec-21` (volumes+cluster+pv+nodes), `sec-30` and `net-2` (sg+cluster+nodes+instances).
m4(){ local id="$1" f1="$2" f2="$3" f3="$4" f4="$5" p="$6" r st d; r=$(jq -r "$B$PE $p" "$W/$f1.json" "$W/$f2.json" "$W/$f3.json" "$W/$f4.json" 2>&1) || { printf 'SCORER ABORT [%s]: jq failed — a missing or malformed collection file is NOT a finding, and must never be scored as one. jq said: %s\n' "$id" "$r" >&2; exit 1; }; [ -n "$r" ] || { printf 'SCORER ABORT [%s]: jq produced no output\n' "$id" >&2; exit 1; }; st="${r%%~*}"; d="${r#*~}"; [ "$r" = "$st" ]&&d=""; emit "$id" measured "${st:-none}" "$d"; }
# Seven inputs, for `sec-4` and `sec-6`. sec-4: NetworkPolicy enforcement is opt-in on BOTH cluster shapes,
# recorded in different places, so it reads the NetworkPolicy objects, the namespaces (denominator), the
# aws-node DaemonSet (standard), the `amazon-vpc-cni` ConfigMap and NodeClasses (Auto Mode), nodes.json
# (cluster shape) and pods.json (namespaces whose pods all run on Fargate).
#
# THE HELPER NAME IS A CONTRACT WITH render-report.py: the number of collection files a helper reads must be
# DERIVABLE FROM ITS NAME. `_SCORER_RE` is `^(m\d*)\s+([a-z]+-\d+)\s+(.*)$` and `_helper_arity()` reads the
# digits; scorer_provenance() builds each question's "Data read", "Exact command used" and "Returned"
# panels from it. Do not narrow it (`m[234]?` or a fixed table would silently drop `sec-4`'s `m7` and ship
# a High finding with no audit trail).
#
# Six inputs, for `net-3`: the sixth, `vpccniconfig`, is bound and not read.
m6(){ local id="$1" f1="$2" f2="$3" f3="$4" f4="$5" f5="$6" f6="$7" p="$8" r st d; r=$(jq -r "$B$PE $p" "$W/$f1.json" "$W/$f2.json" "$W/$f3.json" "$W/$f4.json" "$W/$f5.json" "$W/$f6.json" 2>&1) || { printf 'SCORER ABORT [%s]: jq failed — a missing or malformed collection file is NOT a finding, and must never be scored as one. jq said: %s\n' "$id" "$r" >&2; exit 1; }; [ -n "$r" ] || { printf 'SCORER ABORT [%s]: jq produced no output\n' "$id" >&2; exit 1; }; st="${r%%~*}"; d="${r#*~}"; [ "$r" = "$st" ]&&d=""; emit "$id" measured "${st:-none}" "$d"; }
m7(){ local id="$1" f1="$2" f2="$3" f3="$4" f4="$5" f5="$6" f6="$7" f7="$8" p="$9" r st d; r=$(jq -r "$B$PE $p" "$W/$f1.json" "$W/$f2.json" "$W/$f3.json" "$W/$f4.json" "$W/$f5.json" "$W/$f6.json" "$W/$f7.json" 2>&1) || { printf 'SCORER ABORT [%s]: jq failed — a missing or malformed collection file is NOT a finding, and must never be scored as one. jq said: %s\n' "$id" "$r" >&2; exit 1; }; [ -n "$r" ] || { printf 'SCORER ABORT [%s]: jq produced no output\n' "$id" >&2; exit 1; }; st="${r%%~*}"; d="${r#*~}"; [ "$r" = "$st" ]&&d=""; emit "$id" measured "${st:-none}" "$d"; }

# ── identity-access (13) ──
# sec-1/sec-2/sec-17/sec-26 PRINT FIELD PATHS AND VALUES, so their `rl` programs emit `kind:"field"` with
# the evidence in `pass`. `not set` is emitted for an ABSENT key, not `null`: "the API did not return this
# field" and "returned null" are different facts.
rl sec-1 cluster '(.cluster.resourcesVpcConfig) as $v|{pass:["resourcesVpcConfig.endpointPrivateAccess = "+(if (($v|type)=="object") and ($v|has("endpointPrivateAccess")) then ($v.endpointPrivateAccess|tojson) else "not set" end)],fail:[],kind:"field"}'
# The detail NAMES THE PUBLIC SIDE TOO. `endpointPrivateAccess` and `endpointPublicAccess` are independent:
# both can be on with publicAccessCidrs 0.0.0.0/0, and then sec-1 correctly reads "all" while sec-2 reads
# "none~public 0.0.0.0/0". A bare "private endpoint on" beside a green tick would be read as "not reachable
# from the internet".
m sec-1 cluster '.cluster.resourcesVpcConfig as $v| if $v.endpointPrivateAccess==true then "all~private endpoint on" + (if $v.endpointPublicAccess==true then " (public access is ALSO on -- see sec-2)" else " (public access off)" end) else "none~private endpoint off" end'
# `pj` renders an array as `["a", "b"]` (space after the comma; `tojson` omits it), used for
# `publicAccessCidrs`, the only list a field print emits.
rl sec-2 cluster '(.cluster.resourcesVpcConfig) as $v|def pj: if type=="array" then "["+(map(tojson)|join(", "))+"]" else tojson end;def f($k): "resourcesVpcConfig."+$k+" = "+(if (($v|type)=="object") and ($v|has($k)) then ($v[$k]|pj) else "not set" end);{pass:[f("endpointPublicAccess"),f("publicAccessCidrs")],fail:[],kind:"field"}'
m sec-2 cluster 'def ipnum: split(".") as $o|(if (($o|length)==4) and ([$o[]|tonumber]|all(.>=0 and .<=255)) then ([$o[]|tonumber]|(.[0]*16777216+.[1]*65536+.[2]*256+.[3])) else null end);def iv: (try (split("/") as $q|(if ($q|length)>1 then ($q[1]|tonumber) else 32 end) as $p|($q[0]|ipnum) as $a|(if ($a!=null) and ($p>=0) and ($p<=32) then ((pow(2;32-$p))|floor) as $sz|[(($a/$sz)|floor)*$sz,$sz] else null end)) catch null);.cluster.resourcesVpcConfig as $v|(($v.publicAccessCidrs//[])|map(tostring)) as $c|($c|any(endswith("/0"))) as $lit|[$c[]|{k:.,v:iv}] as $pz|[$pz[]|select(.v==null)|.k] as $bad|[$pz[]|select(.v!=null)|.v] as $good|(if ($good|length)==0 then false else ($good|sort_by(.[0])|reduce .[] as $x ([]; if (length>0) and ($x[0]<=(.[-1][0]+.[-1][1])) then (.[0:-1]+[[.[-1][0],(([.[-1][0]+.[-1][1],$x[0]+$x[1]]|max)-.[-1][0])]]) else .+[$x] end)|(map(.[1])|add)>=4294967296) end) as $cov| if $v.endpointPublicAccess==false then "all~public disabled" elif $lit then "none~public endpoint open to the whole internet — publicAccessCidrs contains a /0 prefix (\($c|join(", ")))" elif $cov then "none~publicAccessCidrs cover the WHOLE IPv4 internet between them (\($c|join(", "))) — equivalent to 0.0.0.0/0" elif ($bad|length)>0 then "some~\($bad|length) of \($c|length) publicAccessCidrs entries are not IPv4 CIDRs this check can parse (\($bad|join(", "))), so total coverage was NOT measured; the \(($c|length)-($bad|length)) that did parse do not reach the whole IPv4 internet" elif ($c|length)>0 then "all~public restricted to \($c|length) CIDR range(s): \($c|join(", ")) — measured as IPv4 coverage, not as whether these are the intended operators" else "none~public open" end'
g sec-3
g sec-5
# sec-6 -- workload identity. Counts BOTH EKS Pod Identity and IRSA. Pod Identity uses NO ServiceAccount
# annotation (associations exist only in the EKS API), so reading only `eks.amazonaws.com/role-arn` would
# report a correct Pod Identity cluster as having none. IRSA also needs the IAM OIDC provider REGISTERED
# (see sec-18). An annotation counts as IRSA only when its value is an IAM role ARN
# (`arn:<partition>:iam::<12-digit account>:role/<path/name>`); the webhook injects nothing for an empty
# value and STS rejects a non-ARN. sec-6 and sec-18 apply the same test.
# The list is `kind:"existence"` (no denominator) and credits exactly what the verdict credits: an association
# is in `pass` only when `m7` credits Pod Identity, an annotation only when its provider is registered; the
# rest go to `context` marked NOT credited, so a NOT ASSESSED or `none` verdict never sits over a non-empty
# pass list.
# Fargate nodes are left out of `$nt`: EKS Pod Identity is not supported on Fargate and DaemonSets do not run
# there, so with only Fargate nodes an association is known unserved and the answer is `none` (IRSA still
# grades first), not NOT ASSESSED. Windows EC2 nodes are left out too and disclosed (`winx`).
# EACH ASSOCIATION IS JOINED TO THE COLLECTED PODS THAT USE IT (same namespace, `spec.serviceAccountName`,
# then `spec.nodeName` to the node list). Pod Identity cannot be used by "Pods that run anywhere except
# Linux Amazon EC2 instances", so an association whose every such Pod runs on Fargate or Windows is NOT
# credited. One Pod on any other node (Linux EC2, Auto Mode, hybrid) keeps it credited, as does a Pod on a
# node the list lacks; finished Pods and Pods with no node are left out of the join and counted in the detail.
rl sec-6 serviceaccounts cluster oidcproviders podidentity nodes daemonsets pods 'input as $cl|input as $op|input as $pi|input as $nd|input as $ds|input as $pd|(($cl.cluster.identity.oidc.issuer // "")|sub("^https://";"")) as $iss|((($iss|length)>0) and ([$op.OpenIDConnectProviderList[]?.Arn // empty]|any(endswith("oidc-provider/"+$iss)))) as $oidcok|([$pi.associations[]?]|length) as $pia|([$nd.items[]?|{key:(.metadata.name//""),value:(if ((.metadata.labels["eks.amazonaws.com/compute-type"]//"")=="fargate") then "f" elif iswin then "w" else "l" end)}]|from_entries) as $km|[$pd.items[]?|select(((.status.phase//"")|IN("Succeeded","Failed"))|not)|select((.spec.nodeName//"")!="")|{ns:(.metadata.namespace//""),sa:(.spec.serviceAccountName//"default"),k:($km[.spec.nodeName]//"u")}] as $pp|[$pd.items[]?|select(((.status.phase//"")|IN("Succeeded","Failed"))|not)|select((.spec.nodeName//"")=="")|{ns:(.metadata.namespace//""),sa:(.spec.serviceAccountName//"default")}] as $pq|[$pd.items[]?|select((.status.phase//"")|IN("Succeeded","Failed"))|{ns:(.metadata.namespace//""),sa:(.spec.serviceAccountName//"default")}] as $pf|[$pi.associations[]?|. as $a|[$pp[]|select(.ns==($a.namespace//"?") and .sa==($a.serviceAccount//"?"))|.k] as $ks|($ks|any(.=="f")) as $kf|($ks|any(.=="w")) as $kw|{p:([$pq[]|select(.ns==($a.namespace//"?") and .sa==($a.serviceAccount//"?"))]|length),d:([$pf[]|select(.ns==($a.namespace//"?") and .sa==($a.serviceAccount//"?"))]|length),s:(($a.namespace//"?")+"/"+($a.serviceAccount//"?")),u:((($ks|length)>0) and ($ks|all(.=="f" or .=="w"))),z:(($ks|length)==0),kd:(if $kf and $kw then "AWS Fargate and Windows nodes" elif $kf then "AWS Fargate nodes" else "Windows nodes" end)}] as $pc|([$pc[]|select(.u|not)]|length) as $piok|([$pc[]|select(.z)]|length) as $pz|([$pc[]|select(.u)]|length) as $pux|([$pc[]|select(.u)|.p]|add//0) as $pup|([$pc[]|select(.z and .p>0)]|length) as $pzp|([$pc[]|select(.u)|.d]|add//0) as $pud|([$pc[]|select(.z and .d>0)]|length) as $pzd|(if $pup>0 and $pud>0 then "live, scheduled" elif $pud>0 then "live" elif $pup>0 then "scheduled" else "collected" end) as $sch|([(if $pup>0 then "\($pup) Pod(s) not yet placed on a node" else empty end),(if $pud>0 then "\($pud) finished (Succeeded or Failed) Pod(s)" else empty end)]|join(" and ")) as $pjn|(if ($pc|any(.u and (.kd|test("Fargate")))) and ($pc|any(.u and (.kd|test("Windows")))) then "AWS Fargate or Windows nodes" elif ($pc|any(.u and (.kd|test("Fargate")))) then "AWS Fargate nodes" else "Windows nodes" end) as $puk|[$nd.items[]?|select(iswin and isec2)|(.metadata.name//"?")] as $wn|($wn|length) as $w|([$nd.items[]?|select((.metadata.labels["eks.amazonaws.com/compute-type"]//"")=="fargate")]|length) as $fg|([$nd.items[]?|select((iswin and isec2)|not)|select((.metadata.labels["eks.amazonaws.com/compute-type"]//"")!="fargate")]|length) as $nt|([$nd.items[]?|select((iswin and isec2)|not)|select(((.metadata.labels["eks.amazonaws.com/compute-type"]//"")|IN("auto","fargate"))|not)]|length) as $nonauto|([$ds.items[]?|select((.metadata.name//"")=="eks-pod-identity-agent")|select((.status.numberReady|numbers)>0)]|length>0) as $agent|($piok>0 and (($nt>0 and $nonauto==0) or $agent)) as $pic|([$pc[]|select(.u|not)|.s]|sort) as $pl|([$pc[]|select(.u)]|sort_by(.s)) as $plx|([.items[]?|select((.metadata.annotations["eks.amazonaws.com/role-arn"]//"")|test("^arn:aws[a-z0-9-]*:iam::[0-9]{12}:role/[!-~]+$"))|((.metadata.namespace//"")+"/"+(.metadata.name//"?")+" -> "+((.metadata.annotations["eks.amazonaws.com/role-arn"]|split("/"))|last))]|sort) as $il|{pass:((if $pic then $pl else [] end)+(if $oidcok then $il else [] end)),fail:[],kind:"existence",context:(["cluster issuer: "+(if ($iss|length)>0 then $iss else "absent" end)]+([$op.OpenIDConnectProviderList[]?|((.Arn//"?")|split("oidc-provider/")|last)|select(.==$iss)]|sort|map("IAM OIDC provider: "+.))+(if $pic then (($plx|map("Pod Identity association NOT credited (every "+(if .p>0 and .d>0 then "live, scheduled" elif .d>0 then "live" elif .p>0 then "scheduled" else "collected" end)+" Pod that uses its ServiceAccount runs on "+.kd+", where AWS documents that EKS Pod Identity is not supported"+(if .p>0 then "; \(.p) Pod(s) not yet placed on a node were not counted" else "" end)+(if .d>0 then "; \(.d) finished (Succeeded or Failed) Pod(s) were not counted" else "" end)+"): "+.s))+([$pc[]|select(.z)]|sort_by(.s)|map("Pod Identity association credited although no "+(if (.p>0 or .d>0) then (if .p>0 and .d>0 then "live, scheduled" elif .d>0 then "live" else "scheduled" end)+" Pod uses its ServiceAccount ("+([(if .p>0 then "\(.p) Pod(s) not yet placed on a node" else empty end),(if .d>0 then "\(.d) finished (Succeeded or Failed) Pod(s)" else empty end)]|join(", "))+")" else "collected Pod uses its ServiceAccount" end)+", so nothing shows it is used: "+.s))) elif ($nt>0 and $piok==0) then ($plx|map("Pod Identity association NOT credited (every "+(if .p>0 and .d>0 then "live, scheduled" elif .d>0 then "live" elif .p>0 then "scheduled" else "collected" end)+" Pod that uses its ServiceAccount runs on "+.kd+", where AWS documents that EKS Pod Identity is not supported"+(if .p>0 then "; \(.p) Pod(s) not yet placed on a node were not counted" else "" end)+(if .d>0 then "; \(.d) finished (Succeeded or Failed) Pod(s) were not counted" else "" end)+"): "+.s)) else ((if $nt==0 then (if $fg>0 then "the only nodes are "+(if $w>0 then "\($w) Windows node(s), which this skill does not assess, and " else "" end)+"\($fg) AWS Fargate node(s), where AWS documents that EKS Pod Identity is not supported," elif $w>0 then "the collection lists no nodes other than Windows nodes, which this skill does not assess, so none is shown to be an EKS Auto Mode node," else "the collection lists no nodes, so none is shown to be an EKS Auto Mode node," end) else "a node is not an EKS Auto Mode node" end) as $why|(if $nt==0 then ($pl+[$plx[]|.s]|sort) else $pl end)|map("Pod Identity association NOT credited ("+$why+" and no eks-pod-identity-agent DaemonSet has a ready Pod): "+.))+(if $nt==0 then [] else ($plx|map("Pod Identity association NOT credited (every "+(if .p>0 and .d>0 then "live, scheduled" elif .d>0 then "live" elif .p>0 then "scheduled" else "collected" end)+" Pod that uses its ServiceAccount runs on "+.kd+", where AWS documents that EKS Pod Identity is not supported"+(if .p>0 then "; \(.p) Pod(s) not yet placed on a node were not counted" else "" end)+(if .d>0 then "; \(.d) finished (Succeeded or Failed) Pod(s) were not counted" else "" end)+"): "+.s)) end) end)+(if $oidcok then [] else ($il|map("IRSA annotation NOT credited (no matching IAM OIDC provider, inert): "+.)) end)+(if $w>0 then ["\($w) Windows node(s) not assessed — this skill supports Linux nodes only"]+$wn else [] end))}'
m7 sec-6 serviceaccounts cluster oidcproviders podidentity nodes daemonsets pods 'input as $cl|input as $op|input as $pi|input as $nd|input as $ds|input as $pd|(($cl.cluster.identity.oidc.issuer // "")|sub("^https://";"")) as $iss|((($iss|length)>0) and ([$op.OpenIDConnectProviderList[]?.Arn // empty]|any(endswith("oidc-provider/"+$iss)))) as $oidcok|([.items[]?|select((.metadata.annotations["eks.amazonaws.com/role-arn"]//"")|test("^arn:aws[a-z0-9-]*:iam::[0-9]{12}:role/[!-~]+$"))]|length) as $irsa|([$pi.associations[]?]|length) as $pia|([$nd.items[]?|{key:(.metadata.name//""),value:(if ((.metadata.labels["eks.amazonaws.com/compute-type"]//"")=="fargate") then "f" elif iswin then "w" else "l" end)}]|from_entries) as $km|[$pd.items[]?|select(((.status.phase//"")|IN("Succeeded","Failed"))|not)|select((.spec.nodeName//"")!="")|{ns:(.metadata.namespace//""),sa:(.spec.serviceAccountName//"default"),k:($km[.spec.nodeName]//"u")}] as $pp|[$pd.items[]?|select(((.status.phase//"")|IN("Succeeded","Failed"))|not)|select((.spec.nodeName//"")=="")|{ns:(.metadata.namespace//""),sa:(.spec.serviceAccountName//"default")}] as $pq|[$pd.items[]?|select((.status.phase//"")|IN("Succeeded","Failed"))|{ns:(.metadata.namespace//""),sa:(.spec.serviceAccountName//"default")}] as $pf|[$pi.associations[]?|. as $a|[$pp[]|select(.ns==($a.namespace//"?") and .sa==($a.serviceAccount//"?"))|.k] as $ks|($ks|any(.=="f")) as $kf|($ks|any(.=="w")) as $kw|{p:([$pq[]|select(.ns==($a.namespace//"?") and .sa==($a.serviceAccount//"?"))]|length),d:([$pf[]|select(.ns==($a.namespace//"?") and .sa==($a.serviceAccount//"?"))]|length),s:(($a.namespace//"?")+"/"+($a.serviceAccount//"?")),u:((($ks|length)>0) and ($ks|all(.=="f" or .=="w"))),z:(($ks|length)==0),kd:(if $kf and $kw then "AWS Fargate and Windows nodes" elif $kf then "AWS Fargate nodes" else "Windows nodes" end)}] as $pc|([$pc[]|select(.u|not)]|length) as $piok|([$pc[]|select(.z)]|length) as $pz|([$pc[]|select(.u)]|length) as $pux|([$pc[]|select(.u)|.p]|add//0) as $pup|([$pc[]|select(.z and .p>0)]|length) as $pzp|([$pc[]|select(.u)|.d]|add//0) as $pud|([$pc[]|select(.z and .d>0)]|length) as $pzd|(if $pup>0 and $pud>0 then "live, scheduled" elif $pud>0 then "live" elif $pup>0 then "scheduled" else "collected" end) as $sch|([(if $pup>0 then "\($pup) Pod(s) not yet placed on a node" else empty end),(if $pud>0 then "\($pud) finished (Succeeded or Failed) Pod(s)" else empty end)]|join(" and ")) as $pjn|(if ($pc|any(.u and (.kd|test("Fargate")))) and ($pc|any(.u and (.kd|test("Windows")))) then "AWS Fargate or Windows nodes" elif ($pc|any(.u and (.kd|test("Fargate")))) then "AWS Fargate nodes" else "Windows nodes" end) as $puk|[$nd.items[]?|select(iswin and isec2)|(.metadata.name//"?")] as $wn|($wn|length) as $w|([$nd.items[]?|select((.metadata.labels["eks.amazonaws.com/compute-type"]//"")=="fargate")]|length) as $fg|([$nd.items[]?|select((iswin and isec2)|not)|select((.metadata.labels["eks.amazonaws.com/compute-type"]//"")!="fargate")]|length) as $nt|([$nd.items[]?|select((iswin and isec2)|not)|select(((.metadata.labels["eks.amazonaws.com/compute-type"]//"")|IN("auto","fargate"))|not)]|length) as $nonauto|([$ds.items[]?|select((.metadata.name//"")=="eks-pod-identity-agent")|select((.status.numberReady|numbers)>0)]|length>0) as $agent|($piok>0 and (($nt>0 and $nonauto==0) or $agent)) as $pic|(if ($pia>0 and ($pic|not)) then " — \($pia) Pod Identity association(s) NOT credited: "+(if $nt>0 and $piok==0 then "every \($sch) Pod that uses their ServiceAccounts runs on \($puk), where AWS documents that EKS Pod Identity is not supported"+(if $pjn!="" then " (\($pjn) were not counted)" else "" end) elif $nt==0 and $fg>0 then "the only nodes are "+(if $w>0 then "\($w) Windows node(s), which this skill does not assess, and " else "" end)+"\($fg) AWS Fargate node(s), where AWS documents that EKS Pod Identity is not supported" elif $nt==0 then "the collection lists no nodes"+(if $w>0 then " other than Windows nodes, which this skill does not assess" else "" end)+", so none is shown to be an EKS Auto Mode node, and no eks-pod-identity-agent DaemonSet has a ready Pod" else "\($nonauto) of \($nt) node(s) are not EKS Auto Mode nodes and no eks-pod-identity-agent DaemonSet has a ready Pod, and AWS documents that agent as a prerequisite on such nodes"+(if $pux>0 then "; \($pux) of the \($pia) association(s) are used only by \($sch) Pods on \($puk), where AWS documents that EKS Pod Identity is not supported"+(if $pjn!="" then " (\($pjn) were not counted)" else "" end) else "" end) end) else "" end) as $pn|((if $pux>0 then " (\($pux) more NOT credited: every \($sch) Pod that uses their ServiceAccounts runs on \($puk), where AWS documents that EKS Pod Identity is not supported"+(if $pjn!="" then "; \($pjn) were not counted" else "" end)+")" else "" end)+(if $pz>0 then " (\($pz) of the credited association(s) are used by no "+(if ($pzp+$pzd)>0 then (if $pzp>0 and $pzd>0 then "live, scheduled" elif $pzd>0 then "live" else "scheduled" end)+" Pod ("+([(if $pzp>0 then "\($pzp) of them only by Pods not yet placed on a node" else empty end),(if $pzd>0 then "\($pzd) of them by finished (Succeeded or Failed) Pods" else empty end)]|join("; "))+")" else "collected Pod" end)+", so nothing shows they are used)" else "" end)) as $px| if $pic and ($oidcok and $irsa>0) then "all~\($piok) Pod Identity assoc + \($irsa) IRSA SAs"+$px+winx($w) elif $pic then "all~\($piok) Pod Identity association(s)"+$px+winx($w) elif ($oidcok and $irsa>0) then "all~\($irsa) IRSA SAs"+$pn+winx($w) elif $pia>0 then (if $nt==0 and $w>0 then winna($w)+(if $irsa>0 then "; the \($irsa) IRSA annotation(s) are inert (no IAM OIDC provider matching the cluster issuer is registered)" else "" end) elif $nt==0 and $fg>0 then "none~no workload identity is in effect"+$pn+(if $irsa>0 then "; the \($irsa) IRSA annotation(s) are inert (no IAM OIDC provider matching the cluster issuer is registered)" else "" end)+", so no node can serve any association; Fargate pods need IRSA" elif $piok==0 then "none~no workload identity is in effect"+$pn+(if $irsa>0 then "; the \($irsa) IRSA annotation(s) are inert (no IAM OIDC provider matching the cluster issuer is registered)" else "" end)+", so no association serves any \($sch) Pod; those Pods need IRSA"+winx($w) else "na~NOT ASSESSED"+$pn+(if $irsa>0 then "; the \($irsa) IRSA annotation(s) are inert (no IAM OIDC provider matching the cluster issuer is registered)" else "" end)+", so whether any association is served was not established — "+(if $nt==0 then "check again once the cluster has nodes" else "check the agent on those nodes" end)+winx($w) end) elif $irsa>0 then "none~\($irsa) IRSA annotation(s) but no IAM OIDC provider matching the cluster issuer is registered — inert"+winx($w) else "none~no workload identity (no Pod Identity associations, no IRSA)"+winx($w) end'
g sec-7
rl sec-9 clusterroles '[.items[]|select(.metadata.name|test("^system:|^eks:|^cluster-admin$")|not)] as $r|[$r[]|select([.rules[]?|select(([.resources[]?]|any(.=="*")) or ([.verbs[]?]|any(.=="*")))]|length==0)] as $p|{pass:[$p[]|(.metadata.name//"?")],fail:[($r-$p)[]|(.metadata.name//"?")]}'
m sec-9 clusterroles '[.items[]|select(.metadata.name|test("^system:|^eks:|^cluster-admin$")|not)] as $r|($r|length) as $t|([$r[]|select([.rules[]?|select(([.resources[]?]|any(.=="*")) or ([.verbs[]?]|any(.=="*")))]|length==0)]|length) as $ok| b($ok;$t)+"~\($ok)/\($t) ClusterRoles carry no literal * resource or verb — the scope excludes only system:*, eks:* and cluster-admin, so the built-in admin, edit and view roles are counted here as if they were custom"'
rl sec-17 cluster '(.cluster.accessConfig) as $v|{pass:["accessConfig.authenticationMode = "+(if (($v|type)=="object") and ($v|has("authenticationMode")) then ($v.authenticationMode|tojson) else "not set" end)],fail:[],kind:"field"}'
m sec-17 cluster '(.cluster.accessConfig.authenticationMode // "CONFIG_MAP") as $mm| if $mm=="API" then "all~API — cluster access is granted by EKS access entries only; the aws-auth ConfigMap is inert on this cluster and its contents were NOT read" elif $mm=="API_AND_CONFIG_MAP" then "some~API_AND_CONFIG_MAP — access entries are active AND the legacy aws-auth ConfigMap still grants access alongside them, to any principal without an access entry; its contents were NOT read" elif $mm=="CONFIG_MAP" then "none~CONFIG_MAP — access is granted only by the legacy aws-auth ConfigMap, with no access entries at all; its contents were NOT read, so which IAM identities it maps is unknown to this review" else "na~authenticationMode \($mm) is one this review does not recognise, so what it grants was NOT ASSESSED rather than assumed" end'
# sec-18 -- the IAM OIDC identity provider must actually EXIST. `cluster.identity.oidc.issuer` is populated
# on every EKS cluster (it is the input to `aws iam create-open-id-connect-provider`, not evidence the
# provider exists); scoring off it alone would be a pass that cannot fail. The issuer (scheme stripped) is
# matched against the provider ARN suffix so a provider of a DIFFERENT cluster in the account does not count.
# `na` when no ServiceAccount carries IRSA: there is no IRSA to enable, and demanding a provider would fire a
# false High on a Pod-Identity-only cluster and double-count sec-6. `none` is reserved for IRSA annotations
# that grant nothing because no matching provider is registered.
# `excluded` is the count of account-scoped providers that do not match this issuer; the count shows they
# were considered without publishing the ARNs (account id included) of other clusters.
rl sec-18 cluster oidcproviders serviceaccounts 'input as $p|input as $sa|((.cluster.identity.oidc.issuer // "")|sub("^https://";"")) as $iss|[$p.OpenIDConnectProviderList[]?|(.Arn//"?")] as $arns|[$arns[]|select(endswith("oidc-provider/"+$iss))] as $match|([$sa.items[]?|select((.metadata.annotations["eks.amazonaws.com/role-arn"]//"")|test("^arn:aws[a-z0-9-]*:iam::[0-9]{12}:role/[!-~]+$"))|(.metadata.namespace//"")+"/"+(.metadata.name//"?")]|sort) as $il|(($match|length)>0) as $ok|{pass:(([$match[]|"IAM OIDC provider: "+.])+(if $ok then ($il|map("IRSA ServiceAccount: "+.)) else [] end)),fail:[],kind:"field",context:(["cluster issuer: "+(if ($iss|length)>0 then $iss else "absent" end)]+(if $ok then [] else ($il|map("IRSA ServiceAccount NOT credited (no IAM OIDC provider matches the cluster issuer, inert): "+.)) end)),excluded:(($arns|length)-($match|length))}'
m3 sec-18 cluster oidcproviders serviceaccounts 'input as $p|input as $sa|((.cluster.identity.oidc.issuer // "")|sub("^https://";"")) as $iss|[$p.OpenIDConnectProviderList[]?.Arn // empty] as $arns|([$sa.items[]?|select((.metadata.annotations["eks.amazonaws.com/role-arn"]//"")|test("^arn:aws[a-z0-9-]*:iam::[0-9]{12}:role/[!-~]+$"))]|length) as $irsa| if $irsa==0 then "na~no IRSA ServiceAccounts, so no IAM OIDC provider is required (workload identity is scored by sec-6)" elif ($iss|length)==0 then "none~\($irsa) IRSA SA(s) but the cluster reports no OIDC issuer" elif ($arns|any(endswith("oidc-provider/"+$iss))) then "all~IAM OIDC provider registered for the cluster issuer (\($irsa) IRSA SAs)" else "none~\($irsa) IRSA SA(s) but NO IAM OIDC provider matches the cluster issuer (\($arns|length) in account) — the annotations grant nothing" end'
# rbac-1 reads aws-auth AS WELL AS the ClusterRoleBindings. `system:masters` is a built-in group whose
# cluster-admin power is baked into the API server (no ClusterRoleBinding needed), so the bindings alone
# cannot see who aws-auth maps INTO it; without `awsauth.json` a cluster handing cluster-admin to an IAM
# role would report `all~system-only`.
# PRESENCE, NOT A COUNT. `data.mapRoles`/`data.mapUsers` are YAML documents carried as JSON strings and jq
# cannot parse YAML. A substring test is robust; splitting into entries to count them is not, so the detail
# carries no `N/M`. The verdict does not depend on the `rl` line's textual ARN attribution.
# ONLY `system:masters` IS MATCHED, not `cluster-admin`: a group of that name grants nothing without a
# ClusterRoleBinding (which the `$ns` clause already reports), and matching the bare string would fire on
# role ARNs like `.../eks-cluster-admin-role`.
# On `authenticationMode` `API` EKS uses access entries only and a ConfigMap left after migrating is inert, so
# `$aa` is `{}` there (any other or missing mode keeps it) and only the bindings decide. Absent aws-auth is never a finding.
# `ti` (attribution) groups `data.mapRoles`/`data.mapUsers` at the MINIMUM indent of any `- ` line and
# regexes `arn:...` and `username:` out of each group. GROUPING AT THE TOP-LEVEL INDENT IS THE POINT:
# splitting on every `- ` cuts a mapping at its nested `groups:` list, so the fragment holding `system:masters`
# has no ARN. When nothing is attributed the BLOCK is named instead.
# THE SUBSTRING TEST RUNS OVER THE TEXT WITH FULL-LINE YAML COMMENTS REMOVED, in BOTH lines: a fully
# `#`-commented break-glass mapping would otherwise publish a named role as holding cluster-admin. The strip
# is `^\s*#` (whole line) plus a trailing comment (whitespace then `#`) -- but EITHER IS STRIPPED ONLY IF THE
# COMMENT TEXT HOLDS NO QUOTE CHARACTER: a line continuing a multi-line quoted scalar
# (`groups: ["a` then `    #b", "system:masters"]`) really grants the group, and a quote-blind strip would
# delete it -- a false Pass. The cost, kept as the lesser wrong: a comment holding a quote
# (`# don't add system:masters`) is not stripped and reads as a grant.
# THE EXEMPTION IS AN ALLOWLIST OF TWO (kind, name) PAIRS, NOT A `system:`/`eks:` PREFIX, in both lines:
# `Group system:masters` (the API server authorizer grants it cluster-admin directly) and
# `User eks:addon-manager` (bound by EKS's own `eks:addon-cluster-admin` ClusterRoleBinding; its power comes
# entirely from that binding). Of the bindings EKS itself creates only those two reach `cluster-admin`;
# re-derive from `clusterrolebindings.json`, since a later EKS release may bind more.
# THE KEY IS kind+name: a name-only list admits `Group eks:addon-manager` (receives nothing from the EKS
# binding, so a binding to it hands cluster-admin to whatever the group contains) and `User system:masters`
# (a different subject from the special-cased GROUP; holds nothing until bound), each a real grant that would
# score `all` with an empty `fail`.
# NOT A PREFIX: `system:`-prefixed names that must never hold cluster-admin are open-ended (`system:anonymous`,
# `system:unauthenticated`, `system:authenticated`, `system:serviceaccounts[:<ns>]`, `system:nodes`,
# `system:bootstrappers`, per-component identities); carving exceptions out of a prefix leaves the rest
# scoring `all~system-only`. A new EKS control-plane identity reads as a finding until added.
# THE TEST IS ON THE SUBJECT, NEVER ON THE BINDING. The `kubernetes.io/bootstrapping: rbac-defaults` label is
# not provenance: the default `cluster-admin` binding carries it, `eks:addon-cluster-admin` does not, and
# anyone can apply it to their own binding; binding names are equally author-controlled. Consequence: an
# operator's SECOND binding of `User eks:addon-manager` to cluster-admin is accepted like EKS's own.
# THE aws-auth HALF IS A TEXT MATCH, and the `all` and `na` arms say so. The EKS authenticator PARSES the YAML,
# so a double-quoted scalar can grant `system:masters` while the raw text never holds the literal (`"\x74"`,
# `"t"`, an escaped line break mid-word or after the colon). `$esc` (a `"` followed by a `\` before the next
# `"`) therefore turns the arm that would say `all` into `na~NOT ASSESSED, AND NOT A PASS`; it over-fires on
# any escaped value, the safe way. No regex can enumerate the escape family (each of the 14 characters of
# system:masters can be \xNN or \uNNNN, and an escaped break can fall at any of 13 interior positions), so the
# check withholds the pass instead of trying to match. An UNescaped line break folds to `system: masters`,
# which is not the group.
# `$tag`: go-yaml (behind sigs.k8s.io/yaml, which the EKS authenticator unmarshals aws-auth with) base64-decodes
# `- !!binary c3lzdGVtOm1hc3RlcnM=` to `system:masters` with no escape and no literal; tags are an open
# family, so any `!` in the raw text withholds the Pass. Anchors/aliases, flow sequences and block scalars
# need no guard: each leaves the literal in the text or folds to `system: masters`.
# `$tpl`: aws-iam-authenticator renders `{{SessionName}}`-style templates in groups too (server.go
# renderTemplates loops over mapping.Groups), so `- system:{{SessionName}}` lets a session named `masters` get
# `system:masters`. A bare `{{` test would fire on nearly every EC2 cluster (`system:node:{{EC2PrivateDNSName}}`),
# so `$tpl` fires only when a template-bearing token could render to exactly `system:masters`: literal parts
# lowercase letters or `:`, each `{{...}}` replaced by `[^:]*` (sound: STS RoleSessionName allows only
# `[\w+=,.@-]`, account IDs are digits, EC2 DNS names and access key IDs hold none). It over-fires on such a
# token in a username or comment, the safe way.
# THE THIRD PATH IS NOT READ AT ALL: EKS access entries are collected nowhere, and on an
# `authenticationMode: API` cluster they are the only mechanism in play (aws-auth is inert). Both facts
# belong beside the verdict.
# THE MATCH IS WRONG IN BOTH DIRECTIONS, so the `none` arm is qualified too: a mapRoles whose `username` is
# `x zz system:masters`, granting only `system:nodes`, scores `none` and prints an innocent role under the
# findings heading. Each arm names the mechanism instead of asserting a fact.
# THE DETAIL SAYS NEITHER "system-only" NOR "nonsystem": those words describe a prefix test.
rl rbac-1 clusterrolebindings awsauth cluster 'input as $a0|input as $cl|(if ($cl.cluster.accessConfig.authenticationMode//"CONFIG_MAP")=="API" then {} else $a0 end) as $aa|def ti($txt): ($txt|split("\n")) as $lines|[$lines[]|select(test("^\\s*-\\s"))|(capture("^(?<sp>\\s*)").sp|length)] as $ind|if ($ind|length)==0 then [$txt] else ($ind|min) as $top|(reduce $lines[] as $ln ({out:[],cur:[]}; if ((.cur|length)>0) and ($ln|test("^\\s*-\\s")) and (($ln|capture("^(?<sp>\\s*)").sp|length)==$top) then {out:(.out+[(.cur|join("\n"))]),cur:[$ln]} else {out:.out,cur:(.cur+[$ln])} end))|(if ((.cur|length)>0) then (.out+[(.cur|join("\n"))]) else .out end) end;[.items[]|select((.roleRef.name//"")=="cluster-admin")] as $bb|[$bb[]|(.metadata.name//"?") as $bn|.subjects[]?|{n:("ClusterRoleBinding "+$bn+" -> "+(.kind//"?")+" "+(.name//"?")),b:(((.kind//"?")+"/"+(.name//"?"))|IN("Group/system:masters","User/eks:addon-manager"))}] as $s|[["mapRoles","mapUsers"][] as $k|($aa.data[$k]) as $raw|(if ($raw|type)=="string" then ([$raw|split("\n")[]|select((test("^\\s*#[^\"\\x27]*$")|not))|(if test("^(?<k>(?:[^\"\\x27\\s]|\\s(?!#)|\"(?:[^\"\\\\]|\\\\.)*\"|\\x27(?:[^\\x27]|\\x27\\x27)*\\x27)*)\\s#[^\"\\x27]*$") then capture("^(?<k>(?:[^\"\\x27\\s]|\\s(?!#)|\"(?:[^\"\\\\]|\\\\.)*\"|\\x27(?:[^\\x27]|\\x27\\x27)*\\x27)*)\\s#[^\"\\x27]*$").k else . end)]|join("\n")) else null end) as $txt|select((($txt|type)=="string") and ($txt|test("system:masters")))|([ti($txt)[]|select(test("system:masters"))|(if test("arn:[^\\s\"\\x27,\\\\]+") then (match("arn:[^\\s\"\\x27,\\\\]+").string) elif test("username:\\s*\\S+") then (match("username:\\s*(\\S+)").captures[0].string) else null end)|select(.!=null)|"aws-auth data."+$k+": "+.+"  ->  system:masters (cluster-admin via IAM)"]) as $named|if ($named|length)>0 then $named[] else "aws-auth data."+$k+" contains a system:masters group entry; the principal could not be attributed by text alone — read the ConfigMap" end] as $iam|{pass:[$s[]|select(.b)|.n],fail:([$s[]|select(.b|not)|.n]+$iam)}'
m3 rbac-1 clusterrolebindings awsauth cluster 'input as $a0|input as $cl|(($cl.cluster.accessConfig.authenticationMode//"CONFIG_MAP")=="API") as $apim|(if $apim then {} else $a0 end) as $aa|(($aa.data.mapRoles//"")+"\n"+($aa.data.mapUsers//"")) as $am0|($am0|test("\"[^\"]*\\\\")) as $esc|($am0|test("!")) as $tag|([$am0|scan("(?:[^\\s\"\\x27#,\\[\\]{}]|\\{\\{[^{}]*\\}\\})*\\{\\{[^{}]*\\}\\}(?:[^\\s\"\\x27#,\\[\\]{}]|\\{\\{[^{}]*\\}\\})*")|select((gsub("\\{\\{[^{}]*\\}\\}";"")|test("^[a-z:]*$")) and (("^"+gsub("\\{\\{[^{}]*\\}\\}";"[^:]*")+"$") as $re|"system:masters"|test($re)))]|unique) as $tt|(($tt|length)>0) as $tpl|([$am0|split("\n")[]|select((test("^\\s*#[^\"\\x27]*$")|not))|(if test("^(?<k>(?:[^\"\\x27\\s]|\\s(?!#)|\"(?:[^\"\\\\]|\\\\.)*\"|\\x27(?:[^\\x27]|\\x27\\x27)*\\x27)*)\\s#[^\"\\x27]*$") then capture("^(?<k>(?:[^\"\\x27\\s]|\\s(?!#)|\"(?:[^\"\\\\]|\\\\.)*\"|\\x27(?:[^\\x27]|\\x27\\x27)*\\x27)*)\\s#[^\"\\x27]*$").k else . end)]|join("\n")) as $am|($am|test("system:masters")) as $iam|[.items[]|select(.roleRef.name=="cluster-admin")] as $bb|([$bb[]|.subjects[]?|select((((.kind//"")+"/"+(.name//""))|IN("Group/system:masters","User/eks:addon-manager"))|not)]|length) as $ns| if $iam then "none~kube-system/aws-auth maps an IAM principal into system:masters (TEXT-MATCHED in data.mapRoles/mapUsers, not YAML-parsed) — cluster-admin granted through IAM, which no ClusterRoleBinding can show"+(if $ns>0 then ", plus \($ns) ClusterRoleBinding cluster-admin subject(s) outside Group system:masters and User eks:addon-manager" else "" end) elif ($bb|length)==0 then "na~NOT ASSESSED: no ClusterRoleBinding grants cluster-admin — and the IAM paths were NOT established clear: "+(if $apim then "aws-auth is inert under authenticationMode API and was not read" else "aws-auth was text-matched, not YAML-parsed" end)+", and EKS access entries were never read" elif ($ns==0 and ($esc or $tag or $tpl)) then "na~NOT ASSESSED, AND NOT A PASS: no ClusterRoleBinding grants cluster-admin outside Group system:masters and User eks:addon-manager, but kube-system/aws-auth data.mapRoles/mapUsers holds "+([(if $esc then "a double-quoted string containing a backslash escape" else empty end),(if $tag then "a ! character, which is how YAML writes a tag (such as !!binary, whose base64 content YAML decodes)" else empty end),(if $tpl then "the IAM authenticator template(s) "+($tt|join(", "))+", each of which this text match cannot rule out rendering to exactly system:masters (aws-iam-authenticator fills {{...}} placeholders in groups as well as usernames, and {{SessionName}} is a session name the caller picks)" else empty end)]|join(" and "))+". "+(if ($esc or $tag) then "YAML "+(if ($esc and $tag) then "decodes escapes and resolves tags" elif $esc then "decodes that escape" else "resolves tags" end)+(if $tpl then ", the authenticator renders templates," else "" end) else "The authenticator renders templates" end)+" and this review does not (aws-auth is TEXT-MATCHED for system:masters, not YAML-parsed"+(if $tpl then " or template-rendered" else "" end)+"), so "+(if ($esc or $tag) then (if ($esc and $tag) then "an escaped or tagged" elif $esc then "an escaped" else "a tagged" end)+(if $tpl then " or templated" else "" end) else "a templated" end)+" spelling of system:masters could not be ruled out; EKS access entries were never read" elif $ns==0 then "all~no cluster-admin subject outside Group system:masters and User eks:addon-manager — but the IAM paths were NOT established clear: "+(if $apim then "aws-auth is inert under authenticationMode API and was not read" else "aws-auth was TEXT-MATCHED for system:masters, not YAML-parsed, and a double-quoted escape (including a line break inserted by an editor) defeats that match" end)+"; EKS access entries were never read" else "none~\($ns) cluster-admin subject(s) outside Group system:masters and User eks:addon-manager" end'
m3 rbac-2 rolebindings clusterrolebindings serviceaccounts 'input as $crb|input as $sa|[.items[]?|select(((.metadata.namespace//"")|test("^(kube-|amazon-)"))|not)|(.metadata.namespace//"") as $bns|.subjects[]?|select(.kind=="ServiceAccount")|(((.namespace//$bns)|if .=="" then $bns else . end)+"/"+.name)]|unique as $ns_bound|[$sa.items[]?|{ns:(.metadata.namespace//""),k:((.metadata.namespace//"")+"/"+(.metadata.name//""))}] as $all|[$crb.items[]?|select(((.roleRef.kind//"")=="ClusterRole" and ((.roleRef.name//"")|IN("system:basic-user","system:discovery","system:public-info-viewer","system:service-account-issuer-discovery","system:cluster-trust-bundle-discovery")))|not)|.subjects[]?|(.name//"") as $n|if .kind=="ServiceAccount" then {ns:(.namespace//""),k:((.namespace//"")+"/"+$n)} elif .kind=="User" and ($n|test("^system:serviceaccount:[^:]+:[^:]+$")) then ($n|split(":")) as $u|{ns:$u[2],k:($u[2]+"/"+$u[3])} elif .kind=="Group" and ($n|IN("system:serviceaccounts","system:authenticated")) then $all[] elif .kind=="Group" and ($n|startswith("system:serviceaccounts:")) then ($n|ltrimstr("system:serviceaccounts:")) as $g|$all[]|select(.ns==$g) else empty end|select((.ns|test("^(kube-|amazon-)"))|not)|.k]|unique as $cluster_bound|(($ns_bound+$cluster_bound)|unique|length) as $t|(($ns_bound-$cluster_bound)|length) as $ok| if $t==0 then "na~no workload ServiceAccount bindings" else b($ok;$t)+"~\($ok)/\($t) SAs namespace-scoped only" end'
m3 rbac-3 rolebindings serviceaccounts clusterrolebindings 'input as $sa|input as $crb| ($sa.items|map(.metadata.namespace+"/"+.metadata.name)) as $known|([.items[]?|select(((.metadata.namespace//"")|test("^(kube-|amazon-)"))|not)|(.metadata.namespace//"") as $bns|.subjects[]?|(if .kind=="ServiceAccount" then [((.namespace//$bns)|if .=="" then $bns else . end)+"/"+.name] elif .kind=="User" and ((.name//"")|test("^system:serviceaccount:[^:]+:[^:]+$")) then ((.name|split(":")) as $u|if ($u[2]|test("^(kube-|amazon-)")) then [] else [$u[2]+"/"+$u[3]] end) else [] end)[]]+[$crb.items[]?|.subjects[]?|select(.kind=="ServiceAccount")|select(((.namespace//"")|test("^(kube-|amazon-)"))|not)|((.namespace//"")+"/"+.name)]+[$crb.items[]?|.subjects[]?|select(.kind=="User" and ((.name//"")|test("^system:serviceaccount:[^:]+:[^:]+$")))|(.name|split(":")) as $u|select(($u[2]|test("^(kube-|amazon-)"))|not)|$u[2]+"/"+$u[3]]) as $refs|($refs|length) as $t|([$refs[]|select(. as $r|$known|index($r))]|length) as $ok| if $t==0 then "na~no workload SA bindings" else b($ok;$t)+"~\($ok)/\($t) resolve" end'
# rbac-4 covers ONLY the ServiceAccount named `default` in each workload namespace (a named SA usually needs
# an API token, so counting every SA would fail owners who set `true` on purpose). Pod-level
# `automountServiceAccountToken: true` on pods running as `default` overrides an SA-level `false`, so a
# `default` SA is credited only when it sets `false` AND no non-terminal pod in its namespace runs as it with
# `true`; rl and m2 apply the same predicate. The pod count carries the same `^(kube-|amazon-)` namespace
# filter as the ServiceAccount denominator, so platform pods are not reported against SAs never counted.
rl rbac-4 serviceaccounts pods 'input as $pp|[.items[]?|select((.metadata.namespace//"")|test("^(kube-|amazon-)")|not)|select(.metadata.name=="default")] as $sa|([$pp.items[]?|select((.metadata.namespace//"")|test("^(kube-|amazon-)")|not)|select((.status.phase//"")|IN("Succeeded","Failed")|not)|select(((.spec.serviceAccountName//"")|if .=="" then "default" else . end)=="default")|select(.spec.automountServiceAccountToken==true)|(.metadata.namespace//"")]|unique) as $ovns|[$sa[]|select(.automountServiceAccountToken==false)|select((.metadata.namespace//"") as $n|$ovns|index($n)|not)] as $p|def n: (.metadata.namespace//"")+"/"+(.metadata.name//"?");{pass:[$p[]|n],fail:[($sa-$p)[]|n]}'
m2 rbac-4 serviceaccounts pods 'input as $p|[.items[]?|select((.metadata.namespace//"")|test("^(kube-|amazon-)")|not)|select(.metadata.name=="default")] as $sa|($sa|length) as $t|[$p.items[]?|select((.metadata.namespace//"")|test("^(kube-|amazon-)")|not)|select((.status.phase//"")|IN("Succeeded","Failed")|not)|select(((.spec.serviceAccountName//"")|if .=="" then "default" else . end)=="default")|select(.spec.automountServiceAccountToken==true)] as $ov|($ov|map(.metadata.namespace//"")|unique) as $ovns|([$sa[]|select(.automountServiceAccountToken==false)|select((.metadata.namespace//"") as $n|$ovns|index($n)|not)]|length) as $ok|($ov|length) as $override| if $t==0 then "na~no default ServiceAccounts in workload namespaces" elif $override>0 then b($ok;$t)+"~\($ok)/\($t) default SAs disable token automount with no pod running as them re-enabling it; \($override) pod(s) running as a default SA re-enable it in their own spec (a pod-level true overrides the SA)" else b($ok;$t)+"~\($ok)/\($t) default SAs disable token automount" end'

# ── data-protection (11) ──
m sec-8 deployments 'if ([.items[]|select(.metadata.name|test("external-secrets"))|select(.metadata.name|test("-(webhook|cert-controller|bitwarden-sdk-server)$")|not)|select((.status.readyReplicas|numbers)>0)]|length)>0 then "all~ESO present" else "none~no Ready ESO controller" end'
g sec-24
g sec-34
g sec-35
# sec-21 also matches `ebs.csi.aws.com/cluster-name`, the tag AWS's cluster-scoped CSI policy uses. It does
# NOT answer `na` when EBS-backed PersistentVolumes exist but nothing carries a cluster tag (dynamically
# provisioned CSI volumes are tagged only if the driver is configured to): `na` is excluded from scoring, so
# that would be a silent pass on a High-severity encryption check.
# THE PV FALLBACK MATCHES EKS AUTO MODE'S CSI DRIVER TOO: `.spec.csi.driver` is not tested against
# `ebs.csi.aws.com` only, because Auto Mode's is `ebs.csi.eks.amazonaws.com`
#   https://docs.aws.amazon.com/eks/latest/userguide/create-storage-class.html
# Otherwise the "NOT SCOPED" branch, which stops the question answering from too little evidence, would be
# blind on Auto Mode. The collector recovers Auto-Mode-hidden volumes by id (the numerator); matching this
# driver lets the branch notice the missing denominator.
# AUTO MODE FULFILS THE NODE HALF NOT THE PV HALF, so the detail says which is which:
#   https://docs.aws.amazon.com/whitepapers/latest/security-overview-amazon-eks-auto-mode/eks-auto-mode-data-plane.html
#   "On EKS Auto Mode nodes, the root and data Amazon EBS volumes are encrypted"
#   https://docs.aws.amazon.com/eks/latest/userguide/auto-security.html
#   "EKS Auto Mode does not fully manage EBS volumes created using Kubernetes persistent storage features"
# The clause is appended after the ratio, never substituted, so `resource_agreement()` still reads the
# LEADING `\($ok)/\($t)` against this question's `rl` line. The Auto Mode test is EVERY EC2 NODE carrying
# the documented label, not `computeConfig.enabled` alone (see sec-30); on a mixed-mode cluster the
# managed-node-group root volumes are the operator's, so no node-half credit is claimed.
# THE AUTO MODE GATE `($cl.cluster.computeConfig.enabled==true) and $t>0 and $auto==$t` is spelled by several
# questions across the pillar files and no gate checks it: CHANGE ONE, CHANGE ALL. The census note at ope-10 in
# references/operational-excellence.md lists them all and gives the command. The condition is identical; the
# surrounding bindings differ. Exceptions: rel-4 (autoscaling is a cluster property, reads the flag alone) and
# sec-4 (asks the node-membership question over `($nt>0 and $nauto==$nt and $hy==0)` and does not read the flag).
# THE SCOPE IS A CLUSTER TAG, ATTACHMENT TO ONE OF THIS CLUSTER'S OWN NODES, OR A PV'S VOLUME ID; the node half is not
# optional: nothing tags the root and data volumes of a managed node group or launch template, so a tag-only
# scope would publish a green `all` with an empty `fail` while untagged volumes on this cluster's nodes are
# unencrypted. Karpenter and Auto Mode DO tag their volumes and are counted either way.
# Instance ids come from `$nd` (`spec.providerID` is `aws:///<az>/<instance-id>`); the node set is `islinux`
# (excludes Fargate, EKS Hybrid, Windows), so a volume attached to a Windows node is out of scope even if
# tagged; the detail names the Windows count (`winx`), and `na` (`winna`) only with no Linux EC2 node and no volume.
# `excluded` IS THE OUT-OF-SCOPE VOLUME COUNT AND MUST NEVER BECOME A LIST: `describe-volumes` is collected
# account- and region-wide, so a volume no clause ties to this cluster belongs to another workload; naming it
# would put account-scoped identifiers for outside resources into a report written to be pasted into tickets.
# THE PV HALF (`$pvid`) IS NOT OPTIONAL EITHER: without `--k8s-tag-cluster-id` the EBS CSI driver tags a volume
# only `ebs.csi.aws.com/cluster=true`, so a detached PV volume (StatefulSet at 0, Released PV) has neither tag
# nor attachment. `split("/")|last` reads the in-tree `aws://<az>/vol-...` form too, as collect.sh's id fetch.
# EVERY INPUT IS BOUND, one fewer than the file count: jq re-runs the program per unbound input; `emit` rejects it.
rl sec-21 volumes cluster pv nodes 'input as $cl|input as $pvs|input as $nd|($cl.cluster.name//"") as $cn|([$pvs.items[]?|(.spec.csi.volumeHandle?,.spec.awsElasticBlockStore.volumeID?)]|map(select((type=="string") and .!="")|split("/")|last)|unique) as $pvid|([$nd.items[]?|select(islinux)|(.spec.providerID//""),(.metadata.name//"")]|map(select((type=="string") and (startswith("aws://") or startswith("i-")))|split("/")|last)|unique) as $iid|[$nd.items[]?|select(iswin and isec2)] as $wnd|[$wnd[]|(.metadata.name//"?")] as $wn|($wn|length) as $w|([$wnd[]|(.spec.providerID//""),(.metadata.name//"")]|map(select((type=="string") and (startswith("aws://") or startswith("i-")))|split("/")|last)|unique) as $wiid|[.Volumes[]?] as $all|[$all[]|select(([.Tags[]?|select((.Key==("kubernetes.io/cluster/"+$cn)) or (((.Key|ascii_downcase)|test("cluster")) and (.Value==$cn)))]|length>0) or ([.Attachments[]?.InstanceId]|any(IN($iid[]))) or ((.VolumeId//"")|IN($pvid[])))|select((([.Attachments[]?.InstanceId]|any(IN($wiid[])))|not))] as $v|[$v[]|select(.Encrypted==true)] as $p|def n: (.VolumeId//"?")+" ("+((.Size//"?")|tostring)+" GiB, "+((.VolumeType//"?")|tostring)+")";if ($v|length)==0 and ([$nd.items[]?|select(islinux)]|length)==0 and $w>0 then {pass:[],fail:[],context:(["\($w) Windows node(s) not assessed — this skill supports Linux nodes only"]+$wn),context_only:true} else {pass:[$p[]|n],fail:[($v-$p)[]|n],excluded:(($all|length)-($v|length))}+(if $w>0 then {context:(["\($w) Windows node(s) not assessed — this skill supports Linux nodes only"]+$wn)} else {} end) end'
m4 sec-21 volumes cluster pv nodes 'input as $cl|input as $pvs|input as $nd|($cl.cluster.name//"") as $cn|([$pvs.items[]?|(.spec.csi.volumeHandle?,.spec.awsElasticBlockStore.volumeID?)]|map(select((type=="string") and .!="")|split("/")|last)|unique) as $pvid|[$nd.items[]?|select(islinux)] as $ec2|[$nd.items[]?|select(iswin and isec2)] as $wnd|($wnd|length) as $w|([$wnd[]|(.spec.providerID//""),(.metadata.name//"")]|map(select((type=="string") and (startswith("aws://") or startswith("i-")))|split("/")|last)|unique) as $wiid|([$nd.items[]?|select(ishy)]|length) as $hy|(if $w>0 then "Linux " else "" end) as $lx|($ec2|length) as $t|([$ec2[]|select((.metadata.labels["eks.amazonaws.com/compute-type"]//"")=="auto")]|length) as $auto|(($cl.cluster.computeConfig.enabled==true) and $t>0 and $auto==$t) as $allauto|([$ec2[]|(.spec.providerID//""),(.metadata.name//"")]|map(select((type=="string") and (startswith("aws://") or startswith("i-")))|split("/")|last)|unique) as $iid|[.Volumes[]?|select(([.Tags[]?|select((.Key==("kubernetes.io/cluster/"+$cn)) or (((.Key|ascii_downcase)|test("cluster")) and (.Value==$cn)))]|length>0) or ([.Attachments[]?.InstanceId]|any(IN($iid[]))) or ((.VolumeId//"")|IN($pvid[])))|select((([.Attachments[]?.InstanceId]|any(IN($wiid[])))|not))] as $v|($v|length) as $vt|([$v[]|select(.Encrypted==true)]|length) as $ok|([$pvs.items[]?|select(.spec.csi.driver=="ebs.csi.aws.com" or .spec.csi.driver=="ebs.csi.eks.amazonaws.com" or (.spec.awsElasticBlockStore!=null))]|length) as $ebspv|(if $allauto then " — every "+(if $w>0 then "Linux " else "" end)+"EC2 node is an EKS Auto Mode node, so the root and data volumes AWS attaches at launch are encrypted by design; the volumes Kubernetes persistent storage provisions stay yours to encrypt (sec-25)" else "" end) as $am| (if $hy>0 then " (\($hy) EKS Hybrid Node(s) are not covered: AWS documents that Amazon EBS volumes and the EBS CSI driver are not compatible with hybrid nodes, so whatever storage they use is outside this measurement)" else "" end) as $hyt| if $vt==0 and $t==0 and $w>0 then winna($w)+$hyt elif $vt==0 and $ebspv>0 then "none~NOT SCOPED: \($ebspv) EBS-backed PersistentVolume(s) exist but none of the volumes they name was found, and no volume carries a cluster tag or is attached to a \($lx)node of this cluster, so encryption could not be checked"+winx($w) elif $vt==0 then "na~no volume carries a cluster tag or is attached to a \($lx)node of this cluster, and there are no EBS-backed PVs"+winx($w) else b($ok;$vt)+"~\($ok)/\($vt) encrypted (cluster vols)"+$am+$hyt+winx($w) end'
# sec-38 measures whether a CUSTOMER-MANAGED key is in use -- not whether envelope encryption exists. AWS
# envelope-encrypts all Kubernetes API data, Secrets included, by default on 1.28+ with an AWS-owned KMS key
# ("doesn't require any action on your part"), so "no envelope encryption" would be a false finding on every
# cluster without a CMK. What is absent is the key policy, CloudTrail trail and revocation control that
# come with your own key.
#   https://docs.aws.amazon.com/eks/latest/userguide/envelope-encryption.html
# `resources` is deprecated ("no longer affects which resources are encrypted") but AWS still returns
# ["secrets"], so matching on it is safe.
m sec-38 cluster '([.cluster.encryptionConfig[]?|select((.resources//[])|index("secrets"))]|first) as $ec| if $ec==null then "none~no customer-managed KMS key: Secrets are envelope-encrypted with the default AWS-owned key, so the key policy, CloudTrail audit trail and revocation are not yours to control" elif (($ec.provider.keyArn//"")|length)>0 then "all~cluster is CONFIGURED to envelope-encrypt with a customer-managed KMS key; whether every Secret that already existed has since been rewritten through that key was NOT checked and cannot be seen from cluster config" else "some~encryptionConfig covers secrets but names no keyArn" end'
g sec-22
# sec-25's provisioner set is CANONICAL and MUST stay character-identical across FOUR SCORER LINES: `sec-25`'s
# `rl` and `m` below and `cost-9`'s `rl` and `m` in references/cost-optimization.md (each question spells the
# set twice, to judge and to name what it judged). EDIT ALL FOUR OR NONE.
# All three names must remain: `ebs.csi.aws.com` (self-managed EBS CSI), `ebs.csi.eks.amazonaws.com` (EKS Auto
# Mode) and `kubernetes.io/aws-ebs` (in-tree legacy).
#   https://docs.aws.amazon.com/eks/latest/userguide/create-storage-class.html
#   "EKS Auto Mode does not create a `StorageClass` for you. You must create a `StorageClass`
#   referencing `ebs.csi.eks.amazonaws.com` to use the storage capability of EKS Auto Mode"
# Without the Auto Mode name this question would answer `na~no EBS StorageClass` on an Auto Mode cluster that
# HAS one (`na` is excluded from scoring). MATCHING IT GRANTS NO CREDIT: the StorageClass is the operator's
# object, so this is detection only. A set without the Auto Mode name is also wrong on a cluster that carries
# an unencrypted legacy gp2 class: it would count only that class and score none past an encrypted Auto Mode
# class.
# Out-of-scope StorageClasses ARE NAMED (unlike sec-21's volumes: they are inside the cluster under review).
# They are `context`, not `fail`, because `parameters.encrypted` is an EBS-CSI parameter that does not exist
# on a non-EBS provisioner.
rl sec-25 storageclasses '[.items[]] as $all|[$all[]|select((.provisioner//"")|test("ebs\\.csi\\.aws\\.com|ebs\\.csi\\.eks\\.amazonaws\\.com|kubernetes\\.io/aws-ebs"))] as $s|[$s[]|select(.parameters.encrypted=="true")] as $p|def n: (.metadata.name//"?")+" (type="+((.parameters.type//"?")|tostring)+", encrypted="+((.parameters.encrypted//"unset")|tostring)+")";{pass:[$p[]|n],fail:[($s-$p)[]|n],context:[($all-$s)[]|(.metadata.name//"?")+" ("+((.provisioner//"?")|tostring)+")"]}'
m sec-25 storageclasses '[.items[]|select((.provisioner//"")|test("ebs\\.csi\\.aws\\.com|ebs\\.csi\\.eks\\.amazonaws\\.com|kubernetes\\.io/aws-ebs"))] as $s|($s|length) as $t|([$s[]|select(.parameters.encrypted=="true")]|length) as $ok| if $t==0 then "na~no EBS StorageClass" else b($ok;$t)+"~\($ok)/\($t) encrypted EBS SC" end'
g sec-23
# sec-27 and rel-16 (references/reliability.md) ask related questions and deliberately do not share a pattern:
# rel-16 tests control-plane Deployment names only and caps at `most`; sec-27 is looser (namespaces EXACTLY
# `istio-system`, `consul`, `linkerd` or a Linkerd extension, so not `consulting-app`; or names
# `istiod|linkerd|consul-connect`), so what rel-16 credits sec-27 credits too. Do not align them; see rel-16's note (`grep -n "^m rel-16 " references/reliability.md`).
m sec-27 deployments 'if ([.items[]?|select(((.metadata.namespace//"")|test("^(istio-system|linkerd(-(viz|jaeger|multicluster|smi))?|consul)$";"i")) or (.metadata.name|test("istiod|linkerd|consul-connect";"i")))|select((.status.readyReplicas|numbers)>0)]|length)>0 then "all~mesh present" else "none~no mesh" end'
# sec-28 judges SIDECAR PRESENCE ONLY: how many workload pods carry a mesh sidecar container, found by its
# exact injected name (`istio-proxy`, `linkerd-proxy`, Consul's `envoy-sidecar`/`consul-dataplane`, which
# Consul suffixes `-<service>` on a multi-port pod), so `my-istio-proxy-exporter` is not one. It reads no
# mesh configuration, so it does not judge whether mTLS is enforced, and every non-na detail says so.
# Only `.spec.containers` is read (a native sidecar in `initContainers` is not seen). Windows pods
# (`iswinpod`) leave the population and are disclosed (`winpx`). The mesh's own pods (exact control-plane
# namespaces such as `istio-system` and `linkerd`, and pods carrying the mesh component labels) leave it too,
# since they run the proxy themselves and would credit a mesh with no meshed workload.
m2 sec-28 pods daemonsets '(input|winds) as $wds|[.items[]?|select((.metadata.namespace//"")|test("^(kube-|amazon-)")|not)|select((.status.phase//"")|IN("Succeeded","Failed")|not)|select(((.metadata.namespace//"")|test("^(istio-(system|ingress|egress)|linkerd(-(viz|jaeger|multicluster|smi))?|consul)$";"i"))|not)|select((.metadata.labels//{}) as $l|(($l|has("linkerd.io/control-plane-component")) or (($l.app//"")=="ztunnel") or (($l.istio//"")|IN("ingressgateway","egressgateway")) or ($l|has("gateway.istio.io/managed")))|not)] as $wl|([$wl[]|select(iswinpod($wds))]|length) as $wp|[$wl[]|select(iswinpod($wds)|not)] as $p|($p|length) as $t|([$p[]|select([.spec.containers[]?.name]|any(test("^(istio-proxy|linkerd-proxy)$|^(envoy-sidecar|consul-dataplane)(-.+)?$")))]|length) as $inj| if $t==0 and $wp>0 then winpna($wp) elif $t==0 then "na~no workload pods" elif $inj==0 then "none~no mesh sidecars"+winpx($wp) else b($inj;$t)+"~\($inj)/\($t) workload pods carry a mesh sidecar (Istio/Linkerd/Consul); the mesh mTLS mode and configuration are NOT assessed"+winpx($wp) end'
# sec-29 reads Ingress only, so its `na` means "no Ingress objects", NOT "nothing is exposed in plaintext"
# (a Service of type LoadBalancer on port 80 has no Ingress).
# `spec.tls` IS NOT THE ONLY PLACE AN EKS INGRESS TERMINATES TLS; testing only it would be a High-severity
# FALSE FAIL on the canonical pattern: the AWS Load Balancer Controller takes the certificate from the
# `certificate-arn` annotation and the listener is the ALB's. The annotation counts unless an explicit
# `listen-ports` has no `HTTPS` entry (a cert on an HTTP-only ALB, `[{"HTTP":80}]`, would be a false Pass);
# that HTTP-only list voids `spec.tls` too. ABSENT `listen-ports` defaults to `[{"HTTP": 80}]` or
# `[{"HTTPS": 443}]` depending on whether certificate-arn is specified (controller annotation guide), so
# the annotation counts. On an ALB-class Ingress (`spec.ingressClassName` or legacy
# `kubernetes.io/ingress.class` = `alb`) a bare `spec.tls` gets HTTP:80, so there it counts only beside an
# HTTPS entry; other classes count it. Not read: custom IngressClass names, ssl-redirect, HTTP beside HTTPS,
# another controller's cert annotation.
m sec-29 ingresses '[.items[]] as $i|($i|length) as $t|([$i[]|select((.metadata.annotations//{}) as $a|(($a|.["alb.ingress.kubernetes.io/listen-ports"])//"") as $lp|(($lp|(try fromjson catch null)|[.[]?|objects|keys[]])|any(.=="HTTPS")) as $https|(((.spec.ingressClassName//"")=="alb") or ((($a|.["kubernetes.io/ingress.class"])//"")=="alb")) as $alb|((((.spec.tls//[])|length)>0) and ((($alb|not) and $lp=="") or $https)) or (((($a|.["alb.ingress.kubernetes.io/certificate-arn"])//"")|length)>0 and ($lp=="" or $https)))]|length) as $ok| if $t==0 then "na~no Ingress objects; TLS on Service type=LoadBalancer is not assessed, so this is not a finding of no plaintext exposure" else b($ok;$t)+"~\($ok)/\($t) TLS" end'

# ── network (8) ──
# sec-4 checks that NetworkPolicies can actually be ENFORCED, not merely that objects exist. Enforcement is
# opt-in (docs.aws.amazon.com/eks/latest/userguide/cni-network-policy-configure.html); without it every
# NetworkPolicy is inert and scoring objects alone would give `all`. It shows as the `aws-eks-nodeagent`
# container in the aws-node DaemonSet or an explicit NETWORK_POLICY_ENFORCING_MODE env var. A
# `calico-node`/`cilium` DaemonSet in kube-system/calico-system with `numberReady`>0 enforces BESIDE the VPC
# CNI, so neither NOT-ENFORCED arm fires with one and the plain ratio is published.
# THE STANDARD-CLUSTER GUARD CANNOT FIRE ON EKS AUTO MODE (no `vpc-cni` add-on, no `aws-node` DaemonSet), so
# Auto Mode is read separately. Its enforcement is OPT-IN:
#   https://docs.aws.amazon.com/eks/latest/userguide/auto-net-pol.html
#   "To use network policies with EKS Auto Mode, you first need to enable the Network Policy Controller
#   by applying a ConfigMap to your cluster."  (`metadata.name: amazon-vpc-cni`, `namespace: kube-system`,
#   `data.enable-network-policy-controller: "true"`)
# ONLY `enable-network-policy-controller` WITH THE EXACT STRING "true" IS THE OPT-IN: amazon-network-policy-
# controller-k8s `pkg/utils/configmap/configmap.go` tests `Data["enable-network-policy-controller"] ==
# "true"`, so "True", "TRUE" or the `enable-network-policy` key shown at
# https://docs.aws.amazon.com/eks/latest/best-practices/autosecure.html turn nothing on.
# THE NODECLASS DOES NOT DECIDE THE VERDICT. auto-net-pol.html titles the NodeClass step "Adjust Network Policy
# Agent configuration in Node Class (Optional)" and says the cluster "is now configured to support Kubernetes
# network policies" after the ConfigMap step alone; create-node-class.html gives only `DefaultAllow` and
# `DefaultDeny`. Failing an absent `spec.networkPolicy` would invent a finding, and treating `DefaultAllow` as
# a pass would invent a credit. So the ConfigMap alone decides and any NodeClass `spec.networkPolicy` is
# REPORTED, not scored. No AWS page states the default when unset, so none is claimed. On an Auto Mode
# cluster the ConfigMap can be absent while NodeClass `default` carries `DefaultAllow`; the not-enforced arm
# names that mistake. Neither it nor its no-policies variant prints a ratio.
# THE GATE IS EVERY EC2 NODE, NOT `computeConfig.enabled` (as sec-30, sec-21, reliability lens-2): a mixed-mode
# cluster has an `aws-node` DaemonSet with a live nodeagent, and
# docs.aws.amazon.com/eks/latest/userguide/eks-add-ons.html says "if your cluster combines Auto mode with other
# compute options like self-managed EC2 instances, Managed Node Groups, or AWS Fargate, these add-ons remain
# necessary." Membership is the label `eks.amazonaws.com/compute-type` = `auto`; cluster.json is not an input.
# Fargate nodes are excluded and $nt>0 is required. `$allauto` (`$nt>0 and $nauto==$nt and $hy==0`) is the node
# population alone, exactly as in the `rl` and `m7` lines; keep them in step, the scorer is the authority. The
# standard guard carries `($allauto|not)` so the two guards never both claim a cluster.
# The Auto Mode arm and the standard NOT-ENFORCED arms carry no `n/m` and are not a pass/fail set: empty
# `pass`/`fail`, `kind:"field"`, and the workload namespaces as `context`.
# STANDARD ENFORCEMENT NEEDS BOTH SWITCHES: `--enable-network-policy=true` on the nodeagent AND
# `enable-network-policy-controller: "true"` in the `amazon-vpc-cni` ConfigMap. The nodeagent flag defaults to
# false when absent. A bare `--enable-network-policy` is a Go bool flag meaning true (the inner `//"true"` in
# `$npflag`); values are read as Go's ParseBool does. The agent uses spf13/pflag, where a repeated flag keeps the
# LAST value, so `$npflag` takes `last`.
# NO ENFORCEMENT EVIDENCE IS NEVER A PASS. The ratio is published only where something is shown to enforce:
# an aws-node DaemonSet in kube-system, every EC2 node an Auto Mode node with the ConfigMap on, or a ready
# calico-node/cilium DaemonSet (`$tpe`). Otherwise: no Linux EC2 or hybrid node means Fargate-only, and
# cni-network-policy.html says VPC CNI policies apply "to Amazon EC2 Linux nodes only. You can't apply the
# policies to Fargate or Windows nodes": `none~NOT ENFORCED`. Linux EC2 nodes not all Auto Mode with no
# aws-node DaemonSet: CNI unidentified, `na~NOT ASSESSED`, except when some are Auto Mode nodes with the
# ConfigMap off (proven unenforced): `none~NOT ENFORCED`. Where `$tpe` publishes the ratio beside such Auto
# Mode nodes, a `most`/`all` bucket is capped at `some`.
# BESIDE EKS HYBRID NODES A READY calico-node/cilium COUNTS FOR THE HYBRID NODES ONLY (`$tph`), unless its ready
# Pod count (`$tpr`) also covers every non-Auto-Mode EC2 node (hybrid-nodes-cni.html: "Cilium is not supported
# by AWS when running on nodes in AWS Cloud"). Otherwise the EC2 nodes still need the VPC CNI's own switches:
# the NOT-ENFORCED arms stay skipped and a `most`/`all` bucket is capped at `some`. Hybrid nodes with no
# ready calico-node/cilium are not shown to enforce: `most`/`all` becomes `na~NOT ASSESSED`.
# THE STANDARD GUARD ASKS `$ds`, NOT `addons.json`: `aws eks list-addons` omits a Helm- or manifest-installed
# VPC CNI, so requiring `vpc-cni` there would not fire on clusters that install the CNI themselves -- a false
# Pass over decorative micro-segmentation.
# A NAMESPACE WHOSE PODS ALL RUN ON AWS FARGATE IS NEVER COUNTED AS ENFORCED (`$fgo`, `$oke`; policies cannot be
# applied to Fargate): a covered namespace in it moves from pass to fail and is named.
# ALL FOUR `aws-node` SELECTORS ARE NAMESPACED TO `kube-system`, and must move together. Unqualified, `$vpccni`
# is set by ANY DaemonSet called `aws-node` (a user DaemonSet in `apps` on a Cilium cluster would publish a
# false `none~NOT ENFORCED`), and `$mode`, `$agent`, `$npflag` must read the same DaemonSet.
# Windows nodes leave the node set and are disclosed (`winx`). `$allauto` is decided on Linux EC2 nodes alone:
# gating on the Windows count would send an all-Auto-Mode Linux fleet to the standard arm, which passes on
# objects nothing enforces. `na` (`winna`) only when every node is Windows.
rl sec-4 networkpolicies namespaces daemonsets pods vpccniconfig nodeclasses nodes 'input as $ns|input as $ds|input as $pd|input as $cm|input as $nc|input as $nd|[$nd.items[]?|select(islinux)] as $ec2|([$nd.items[]?|select(iswin|not)]|length) as $nw|[$nd.items[]?|select(iswin and isec2)|(.metadata.name//"?")] as $wn|($wn|length) as $w|($ec2|length) as $nt|([$ec2[]|select((.metadata.labels["eks.amazonaws.com/compute-type"]//"")=="auto")]|length) as $nauto|([$nd.items[]?|select(ishy)]|length) as $hy|($nt>0 and $nauto==$nt and $hy==0) as $allauto|(($cm.data["enable-network-policy-controller"]//"")=="true") as $npc|([$ds.items[]?|select((.metadata.name=="aws-node" and (.metadata.namespace//"")=="kube-system"))]|length>0) as $vpccni|([$ds.items[]?|select((.metadata.name=="aws-node" and (.metadata.namespace//"")=="kube-system"))|.spec.template.spec.containers[]?|select(.name=="aws-eks-nodeagent")]|length>0) as $agent|([$ds.items[]?|select((.metadata.name=="aws-node" and (.metadata.namespace//"")=="kube-system"))|.spec.template.spec.containers[]?|select(.name=="aws-eks-nodeagent")|(.args//[])[]|select(startswith("--enable-network-policy"))|((split("=")[1])//"true")]|last) as $npflag|([$ds.items[]?|select(((.metadata.name=="calico-node") or (.metadata.name=="cilium")) and ((.metadata.namespace//"")|IN("kube-system","calico-system")))|select((.status.numberReady|numbers)>0)]|length>0) as $tpe|(($allauto|not) and (($nt==0 and $hy>0)|not) and ($tpe|not) and (($vpccni and ($agent|not)) or ($agent and ((($npflag//"false")|IN("1","t","T","TRUE","true","True")|not) or ($npc|not))))) as $unenf|[$ns.items[]|select(.metadata.name|test("^(kube-|amazon-)")|not)|(.metadata.name//"?")] as $n|([.items[].metadata.namespace]|unique) as $cov|([$n[]|select(. as $x|$cov|index($x))]|length) as $ok|([$nd.items[]?|select((.metadata.labels["eks.amazonaws.com/compute-type"]//"")=="fargate")|(.metadata.name//"")]) as $fgn|([$pd.items[]?|select((.status.phase//"")|IN("Succeeded","Failed")|not)|select((.spec.nodeName//"")!="")|{ns:(.metadata.namespace//""),f:(.spec.nodeName as $x|($fgn|index($x))!=null)}]|group_by(.ns)|map(select(all(.[];.f))|.[0].ns)) as $fgo|([$n[]|select(. as $x|($cov|index($x)) and ($fgo|index($x)))]|length) as $fgc|($ok - $fgc) as $oke|(($unenf|not) and ($tpe|not) and ($nt==0 and $hy==0)) as $fgonly|(($unenf|not) and ($allauto|not) and ($nt>0) and ($vpccni|not) and ($tpe|not) and (($nauto>0 and ($npc|not)) or ($ok>0 and $nauto<$nt))) as $unid|(($unenf|not) and ($unid|not) and $hy>0 and $nt>0 and ($tpe|not) and (b($oke;($n|length))|IN("all","most"))) as $hyna|(if $w>0 then "Linux " else "" end) as $lx|(if $w>0 then ["\($w) Windows node(s) not assessed — this skill supports Linux nodes only"]+$wn else [] end) as $wc|if $nw==0 and $w>0 then {pass:[],fail:[],context:$wc,context_only:true} elif ($allauto and ($npc|not)) then {pass:[],fail:[],kind:"field",context:(["amazon-vpc-cni ConfigMap: the Network Policy Controller is not enabled, so no NetworkPolicy in this cluster is enforced"]+[$n[]|. as $x|.+" — "+(if ($cov|index($x)) then "has" else "has no" end)+" NetworkPolicy (unenforced either way)"]+$wc)} elif $unenf then {pass:[],fail:[],kind:"field",context:([(if ($agent|not) then "aws-node DaemonSet: the aws-eks-nodeagent container is not running" else "aws-eks-nodeagent: "+(if $npflag==null then "no --enable-network-policy argument (it defaults to false)" else "--enable-network-policy=\($npflag)" end)+"; amazon-vpc-cni ConfigMap enable-network-policy-controller "+(if $npc then "is true" else "is not true" end) end)+", so no NetworkPolicy in this cluster is enforced"]+[$n[]|. as $x|.+" — "+(if ($cov|index($x)) then "has" else "has no" end)+" NetworkPolicy (unenforced either way)"]+$wc)} elif ($fgonly or $unid) then {pass:[],fail:[],kind:"field",context:([(if $fgonly then "no Linux EC2 node and no EKS Hybrid Node: Amazon VPC CNI network policies apply to EC2 Linux nodes only, not to Fargate, so no NetworkPolicy in this cluster is enforced" elif ($nauto>0 and ($npc|not)) then "\($nauto) EKS Auto Mode node(s): the amazon-vpc-cni ConfigMap does not set enable-network-policy-controller to true, so no NetworkPolicy is enforced for pods on those nodes"+(if $nt>$nauto then "; the other \($nt - $nauto) \($lx)EC2 node(s) run no aws-node DaemonSet from kube-system and no ready calico-node or cilium DaemonSet" else "" end)+(if $hy>0 then "; the \($hy) EKS Hybrid Node(s) run no ready calico-node or cilium DaemonSet (the VPC CNI is incompatible with hybrid nodes)" else "" end)+", so no NetworkPolicy in this cluster is shown to be enforced" else "no aws-node DaemonSet in kube-system and no ready calico-node or cilium DaemonSet: the CNI is not identified in the collected data, so enforcement was not measured" end)]+[$n[]|. as $x|.+" — "+(if ($cov|index($x)) then "has" else "has no" end)+" NetworkPolicy"+(if ($fgonly or ($nauto>0 and ($npc|not))) then " (unenforced either way)" else " (enforcement not measured)" end)]+$wc)} elif $hyna then {pass:[],fail:[],kind:"field",context:(["the collected VPC CNI settings show NetworkPolicy enforced on the \($nt) \($lx)EC2 node(s), but the \($hy) EKS Hybrid Node(s) run no ready calico-node or cilium DaemonSet (the VPC CNI is incompatible with hybrid nodes), so enforcement on them was not measured"]+[$n[]|. as $x|.+" — "+(if ($cov|index($x)) then "has" else "has no" end)+" NetworkPolicy (enforcement on the hybrid nodes not measured)"]+$wc)} else [$n[]|select(. as $x|($cov|index($x)) and (($fgo|index($x))|not))] as $p|{pass:$p,fail:($n-$p)}+(if $w>0 then {context:$wc} else {} end) end'
m7 sec-4 networkpolicies namespaces daemonsets pods vpccniconfig nodeclasses nodes 'input as $ns|input as $ds|input as $pd|input as $cm|input as $nc|input as $nd|([$ds.items[]?|select((.metadata.name=="aws-node" and (.metadata.namespace//"")=="kube-system"))]|length>0) as $vpccni|([$ds.items[]?|select((.metadata.name=="aws-node" and (.metadata.namespace//"")=="kube-system"))|.spec.template.spec.containers[]?.env[]?|select(.name=="NETWORK_POLICY_ENFORCING_MODE")|.value]|first) as $mode|([$ds.items[]?|select((.metadata.name=="aws-node" and (.metadata.namespace//"")=="kube-system"))|.spec.template.spec.containers[]?|select(.name=="aws-eks-nodeagent")]|length>0) as $agent|([$ds.items[]?|select((.metadata.name=="aws-node" and (.metadata.namespace//"")=="kube-system"))|.spec.template.spec.containers[]?|select(.name=="aws-eks-nodeagent")|(.args//[])[]|select(startswith("--enable-network-policy"))|((split("=")[1])//"true")]|last) as $npflag|([$ds.items[]?|select(((.metadata.name=="calico-node") or (.metadata.name=="cilium")) and ((.metadata.namespace//"")|IN("kube-system","calico-system")))|select((.status.numberReady|numbers)>0)]|length>0) as $tpe|[$nd.items[]?|select(islinux)] as $ec2|([$nd.items[]?|select(iswin|not)]|length) as $nw|([$nd.items[]?|select(iswin and isec2)]|length) as $w|($ec2|length) as $nt|([$nd.items[]?|select(ishy)]|length) as $hy|([$nd.items[]?|select((.metadata.labels["eks.amazonaws.com/compute-type"]//"")=="fargate")]|length) as $fg|([$ec2[]|select((.metadata.labels["eks.amazonaws.com/compute-type"]//"")=="auto")]|length) as $nauto|($nt>0 and $nauto==$nt and $hy==0) as $allauto|(if $w>0 then "Linux " else "" end) as $lx|(($cm.data["enable-network-policy-controller"]//"")=="true") as $npc|("the aws-eks-nodeagent container on the aws-node DaemonSet runs with "+(if $npflag==null then "no --enable-network-policy argument (it defaults to false)" else "--enable-network-policy=\($npflag)" end)+" and the amazon-vpc-cni ConfigMap in kube-system "+(if $npc then "sets enable-network-policy-controller to true" else "does not set enable-network-policy-controller to true" end)+" (enforcement needs both)") as $npset|([$ds.items[]?|select(((.metadata.name=="calico-node") or (.metadata.name=="cilium")) and ((.metadata.namespace//"")|IN("kube-system","calico-system")))|(.status.numberReady|numbers)]|add//0) as $tpr|($tpe and $hy>0 and $nt>$nauto and $tpr<($hy+$nt-$nauto) and (($agent and (($npflag//"false")|IN("1","t","T","TRUE","true","True")) and $npc)|not)) as $tph|([$nc.items[]?|select(((.spec.networkPolicy//"")|tostring)!="")|"\(.metadata.name)=\(.spec.networkPolicy)"]|join(", ")) as $ncpol|[$ns.items[]|select(.metadata.name|test("^(kube-|amazon-)")|not)|.metadata.name] as $n|($n|length) as $t|([.items[].metadata.namespace]|unique) as $cov|([$n[]|select(. as $x|$cov|index($x))]|length) as $ok|([$nd.items[]?|select((.metadata.labels["eks.amazonaws.com/compute-type"]//"")=="fargate")|(.metadata.name//"")]) as $fgn|([$pd.items[]?|select((.status.phase//"")|IN("Succeeded","Failed")|not)|select((.spec.nodeName//"")!="")|{ns:(.metadata.namespace//""),f:(.spec.nodeName as $x|($fgn|index($x))!=null)}]|group_by(.ns)|map(select(all(.[];.f))|.[0].ns)) as $fgo|([$n[]|select(. as $x|($cov|index($x)) and ($fgo|index($x)))]|length) as $fgc|($ok - $fgc) as $oke| if $nw==0 and $w>0 then winna($w) else (if $t==0 then "na~no workload namespaces" elif ($nt==0 and $hy>0) then "na~NOT ASSESSED: NetworkPolicy enforcement on this cluster is not the Amazon VPC CNI to perform — there are no \($lx)EC2 nodes and \($hy) EKS Hybrid Node(s), and AWS documents that the VPC CNI is not compatible with hybrid nodes and ships its aws-node DaemonSet with anti-affinity for eks.amazonaws.com/compute-type=hybrid. Enforcement here belongs to the Cilium or Calico installation that hybrid nodes require, which this review does not collect, so whether the \($ok) of \($t) workload namespace(s) carrying a NetworkPolicy are enforced was NOT measured" elif ($allauto and ($npc|not)) then (if $ok>0 then "none~every \($lx)EC2 node is an EKS Auto Mode node and the amazon-vpc-cni ConfigMap in kube-system does not enable the Network Policy Controller, so the NetworkPolicy objects that exist in this cluster are NOT enforced — Auto Mode enforcement is opt-in and was never opted into" else "none~every \($lx)EC2 node is an EKS Auto Mode node, the amazon-vpc-cni ConfigMap in kube-system does not enable the Network Policy Controller, and no workload namespace carries a NetworkPolicy — Auto Mode enforcement is opt-in and was never opted into, so pod-to-pod traffic is unrestricted" end) + (if $ncpol!="" then " (NodeClass networkPolicy \($ncpol) IS set, but that is the documented-optional step 3 and it does not enable the controller — apply the ConfigMap)" else "" end) elif ($allauto|not) and $vpccni and ($agent|not) and ($tpe|not) then "none~NOT ENFORCED: the VPC CNI network-policy agent (the aws-eks-nodeagent container on the aws-node DaemonSet) is not running, so no NetworkPolicy in this cluster is enforced — \($ok) of \($t) workload namespace(s) carry one" elif ($allauto|not) and $agent and ((($npflag//"false")|IN("1","t","T","TRUE","true","True")|not) or ($npc|not)) and ($tpe|not) then (if $ok>0 then "none~NOT ENFORCED: \($npset), so the VPC CNI enforces none of the NetworkPolicy objects in this cluster — \($ok) of \($t) workload namespace(s) carry one, and the traffic flows here are identical to a cluster with none" else "none~NOT ENFORCED, and nothing to enforce: \($ok) of \($t) workload namespace(s) carry a NetworkPolicy, and \($npset), so nothing would enforce one if it were added" end) + ". VPC CNI network policy enforcement is opt-in and was never opted into" elif $nt==0 and ($tpe|not) then "none~NOT ENFORCED: this cluster has no \($lx)EC2 node and no EKS Hybrid Node"+(if $fg>0 then " — its \($fg) node(s) are AWS Fargate nodes" else "" end)+", and AWS documents that Amazon VPC CNI network policies apply to Amazon EC2 Linux nodes only and cannot be applied to Fargate, while no calico-node or cilium DaemonSet has a ready Pod, so no NetworkPolicy in this cluster is enforced — \($ok) of \($t) workload namespace(s) carry one" elif ($allauto|not) and ($vpccni|not) and ($tpe|not) and $nauto>0 and ($npc|not) then "none~NOT ENFORCED: \($nauto) of \($nt) \($lx)EC2 nodes are EKS Auto Mode nodes, and the amazon-vpc-cni ConfigMap in kube-system does not set enable-network-policy-controller to true, so no NetworkPolicy is enforced for pods on those \($nauto) nodes"+(if $nt>$nauto then "; the other \($nt - $nauto) \($lx)EC2 node(s) run neither an aws-node DaemonSet from kube-system nor a calico-node or cilium DaemonSet with a ready Pod, so nothing collected shows enforcement there either" else "" end)+(if $hy>0 then "; the \($hy) EKS Hybrid Node(s) on this cluster are not in that \($nt) — AWS documents the Amazon VPC CNI as incompatible with a hybrid node, so enforcement there belongs to Cilium or Calico, and no calico-node or cilium DaemonSet in kube-system or calico-system has a ready Pod, so nothing collected shows enforcement on those \($hy) node(s) either" else "" end)+" — \($ok) of \($t) workload namespace(s) carry a NetworkPolicy" elif ($allauto|not) and ($vpccni|not) and ($tpe|not) and $ok>0 and $nauto<$nt then "na~NOT ASSESSED — no aws-node DaemonSet runs in kube-system and no calico-node or cilium DaemonSet in kube-system or calico-system has a ready Pod, so the CNI networking "+(if $nauto>0 then "the \($nt - $nauto) non-Auto-Mode \($lx)EC2 node(s) of \($nt)" else "the \($nt) \($lx)EC2 node(s)" end)+" is not identified in the collected data and nothing collected shows that it enforces NetworkPolicy, so whether the NetworkPolicy objects in \($ok) of \($t) workload namespace(s) are enforced was NOT measured"+(if $nauto>0 then " (the \($nauto) EKS Auto Mode node(s) enforce: the amazon-vpc-cni ConfigMap enables the Network Policy Controller)" else "" end) elif $hy>0 and ($tpe|not) and (b($oke;$t)|IN("all","most")) then "na~NOT ASSESSED — \($ok) of \($t) workload namespace(s) carry a NetworkPolicy and the collected VPC CNI settings show it enforced on the \($nt) \($lx)EC2 node(s), but the \($hy) EKS Hybrid Node(s) on this cluster were not measured: AWS documents the Amazon VPC CNI as incompatible with a hybrid node, so enforcement there belongs to Cilium or Calico, and no calico-node or cilium DaemonSet in kube-system or calico-system has a ready Pod, so nothing collected shows which CNI runs on those \($hy) node(s) or whether it enforces NetworkPolicy for pods on them" else (if (((($allauto|not) and $nauto>0 and ($npc|not)) or $tph) and (b($oke;$t)|IN("all","most"))) then "some~PARTLY ENFORCED: \($oke) of \($t) ns with a NetworkPolicy" else b($oke;$t)+"~\($oke)/\($t) ns with a NetworkPolicy" end) + (if $fgc>0 then " — \($fgc) more workload namespace(s) carry a NetworkPolicy but run their pods only on AWS Fargate nodes, where AWS documents that VPC CNI network policies cannot be applied, so they are counted as not enforced" else "" end) + (if $mode!=null then " (CNI mode: \($mode))" else "" end) + (if ($allauto and $npc) then " (Auto Mode Network Policy Controller enabled" + (if $ncpol!="" then "; NodeClass networkPolicy \($ncpol), reported not scored" else "" end) + ")" else "" end) + (if (($allauto|not) and $nauto>0 and ($npc|not)) then " — but \($nauto) of \($nt) \($lx)EC2 nodes are EKS Auto Mode nodes, whose enforcement is gated separately by the amazon-vpc-cni ConfigMap and is not enabled, so no policy is enforced for pods landing there"+(if $hy>0 then " (that \($nt) is \($lx)EC2 nodes only — the \($hy) EKS Hybrid Node(s) on this cluster were never in it, because AWS documents the Amazon VPC CNI as incompatible with a hybrid node, so VPC CNI enforcement is not the mechanism there)" else "" end) else "" end) + (if $tph then " — but the ready calico-node or cilium DaemonSet has \($tpr) ready Pod(s), fewer than the \($hy) EKS Hybrid Node(s) plus the \($nt - $nauto) non-Auto-Mode \($lx)EC2 node(s), so it is counted for the hybrid nodes only: AWS supports Cilium on hybrid nodes and not on nodes in AWS Cloud, and its documented install pins the agent to hybrid nodes. On those EC2 node(s) "+(if ($vpccni|not) then "no aws-node DaemonSet runs from kube-system" elif ($agent|not) then "the aws-node DaemonSet runs no aws-eks-nodeagent container" else $npset end)+", so nothing collected shows NetworkPolicy enforced for pods landing there" else "" end) + (if ($hy>0 and ($tpe|not)) then (if ($vpccni|not) and $nauto<$nt then " — the \($hy) EKS Hybrid Node(s) on this cluster run" else " — enforcement was measured on the \($nt) \($lx)EC2 node(s) only: the \($hy) EKS Hybrid Node(s) on this cluster run" end)+" no ready calico-node or cilium DaemonSet (the Amazon VPC CNI is incompatible with a hybrid node), so nothing collected shows whether NetworkPolicy is enforced for pods on them" else "" end) end)+winx($w) end'
g sec-14
# sec-30 asks whether SSH to the nodes is disabled. On EKS Auto Mode nodes THE SECURITY GROUP IS THE WRONG
# EVIDENCE, because there is no listener for port 22:
#   https://docs.aws.amazon.com/eks/latest/userguide/auto-security.html
#   "SSH access is not available." / "AWS Systems Manager Session Manager (SSM) access is not available."
#   https://docs.aws.amazon.com/whitepapers/latest/security-overview-amazon-eks-auto-mode/eks-auto-mode-data-plane.html
#   "remote access services like SSH and the AWS Systems Manager agent are not available on Auto Mode nodes"
# So on an all-Auto-Mode cluster the control is met by the platform and an open port 22 in a cluster
# security group grants nothing.
# THE GATE IS EVERY EC2 NODE CARRYING THE DOCUMENTED LABEL `eks.amazonaws.com/compute-type=auto` (as sec-21
# and reliability lens-2). Fargate nodes are excluded from the denominator and $t>0 is required so an empty
# cluster is never credited vacuously. ON A MIXED-MODE CLUSTER IT FALLS THROUGH to the security-group
# measurement, because a managed node group does run sshd. The detail names the open-SG rule it declines to
# apply and points at net-2, so "SSH is not reachable" is never misread as "this security group is fine".
# sec-30's AUTO MODE ARM IS NOT A PASS/FAIL SET: the cluster setting and node population settle the verdict
# before any `IpPermissions` entry is read, so `pass` and `fail` are EMPTY (listing security groups as
# "Counted as passing" would be a false High-severity Pass; nothing may reintroduce that), `kind:"field"` is
# set because a CLUSTER SETTING decided this, and the security groups stay as `context`, each suffixed with
# why it was not measured. On every other shape the groups are the evidence. Both arms share one
# `context_label` (`SCORER_LIST_UI` is static per question), so the arm-specific words live in the strings.
# Windows nodes leave sec-30's node set and are disclosed (`winx`) on every arm. A cluster security group
# attached only to Windows node instances is left out of the measured set, counted in the detail and listed
# in `context`; a group on any other instance or none, and the cluster's own groups ($own, also on the
# control-plane ENIs and Fargate pods), stay measured.
# THE MEASURED SET INCLUDES EVERY GROUP ON A LINUX NODE INSTANCE (`$lsg`), tagged or not: a launch-template or
# self-managed node SG with no cluster tag still carries port 22. net-2 reads the same set. A Windows node
# with no instance record is counted too (its groups cannot be told apart and stay measured).
rl sec-30 sg cluster nodes instances 'input as $cl|input as $nd|input as $inst|($cl.cluster.name//"") as $cn|([$nd.items[]?|select(ishy)]|length) as $hy|($cl.cluster.resourcesVpcConfig) as $v|((($v.securityGroupIds//[]) + [$v.clusterSecurityGroupId//empty])|unique) as $own|[$nd.items[]?|select(islinux)] as $ec2|[$nd.items[]?|select(iswin and isec2)|(.metadata.name//"?")] as $wn|($wn|length) as $w|($ec2|length) as $t|([$ec2[]|select((.metadata.labels["eks.amazonaws.com/compute-type"]//"")=="auto")]|length) as $auto|[$nd.items[]?|select(iswin and isec2)|((.spec.providerID//"")|split("/")|last)] as $wids|[$inst.Reservations[]?.Instances[]?] as $ins|def isw: (((.Platform//"")|ascii_downcase)=="windows") or (.InstanceId as $i|$wids|index($i));def sgs: [(.SecurityGroups[]?.GroupId),(.NetworkInterfaces[]?.Groups[]?.GroupId)]|map(select(.!=null));([$ins[]|select(isw)|sgs[]]|unique) as $wsg|([$ins[]|select(isw|not)|sgs[]]|unique) as $lsg|($wsg-$lsg-$own) as $wo|([$wids[]|select(. as $i|[$ins[]|select(isw)|.InstanceId]|index($i)|not)]|length) as $wmiss|[.SecurityGroups[]?] as $all|[$all[]|select((.GroupId as $id|$own|index($id)) or ([.Tags[]?|select((.Key==("kubernetes.io/cluster/"+$cn)) or (.Value==$cn))]|length>0) or (.GroupId as $id|$lsg|index($id)) or (.GroupId as $id|$wsg|index($id)))] as $g|def n: (.GroupId//"?")+" ("+((.GroupName//"?")|tostring)+")";(if $w>0 then ["\($w) Windows node(s) not assessed — this skill supports Linux nodes only"]+$wn else [] end) as $wc|[$g[]|select(.GroupId as $id|$wo|index($id))] as $gw|[$g[]|select(.GroupId as $id|$wo|index($id)|not)] as $gl|($wc+[$gw[]|n+" — attached only to Windows nodes, NOT measured by this check"]+(if $wmiss>0 then ["\($wmiss) Windows node(s) have no instance record, so a security group attached only to them cannot be told apart and IS measured"] else [] end)) as $wc2|(if $w>0 then "Linux " else "" end) as $lx|if (($cl.cluster.computeConfig.enabled==true) and $t>0 and $auto==$t and $hy==0) then {pass:[],fail:[],kind:"field",context:(["computeConfig.enabled = true, and every \($lx)EC2 node carries eks.amazonaws.com/compute-type=auto: SSH and the SSM agent are not available on an EKS Auto Mode node, so no port-22 rule can reach a listener and this check was decided without reading one (net-2 still measures 0.0.0.0/0 on every other port)"]+[$gl[]|n+" — in scope for net-2, but NOT measured by this check"]+$wc+[$gw[]|n+" — attached only to Windows nodes, NOT measured by this check"])} elif ($w>0 and ([$nd.items[]?|select(iswin|not)]|length)==0) then {pass:[],fail:[],context:$wc,context_only:true} else [$gl[]|select([.IpPermissions[]?|select((.IpProtocol=="-1" or (((((.IpProtocol//"")|tostring|ascii_downcase) as $pr|($pr=="tcp" or $pr=="6"))) and (.FromPort//0)<=22 and (.ToPort//0)>=22)) and (([.IpRanges[]?.CidrIp]|any(.=="0.0.0.0/0")) or ([.Ipv6Ranges[]?.CidrIpv6]|any(.=="::/0"))))]|length==0)] as $p|{pass:[$p[]|n],fail:[($gl-$p)[]|n],excluded:(($all|length)-($g|length))}+(if $w>0 then {context:$wc2} else {} end) end'
m4 sec-30 sg cluster nodes instances 'input as $cl|input as $nd|input as $inst|($cl.cluster.name//"") as $cn|([$nd.items[]?|select(ishy)]|length) as $hy|(if $hy>0 then " — NOT ASSESSED for the \($hy) EKS Hybrid Node(s) here: a hybrid node is not an EC2 instance and has no EC2 security group, so no rule in this measurement governs SSH to it. Its sshd is the operator to reach and restrict, and the cluster security group carries only the control-plane ingress AWS adds for the remote node and pod CIDRs" else "" end) as $hysg|($cl.cluster.resourcesVpcConfig) as $v|((($v.securityGroupIds//[]) + [$v.clusterSecurityGroupId//empty])|unique) as $own|[$nd.items[]?|select(islinux)] as $ec2|([$nd.items[]?|select(iswin and isec2)]|length) as $w|($ec2|length) as $t|([$ec2[]|select((.metadata.labels["eks.amazonaws.com/compute-type"]//"")=="auto")]|length) as $auto|[$nd.items[]?|select(iswin and isec2)|((.spec.providerID//"")|split("/")|last)] as $wids|[$inst.Reservations[]?.Instances[]?] as $ins|def isw: (((.Platform//"")|ascii_downcase)=="windows") or (.InstanceId as $i|$wids|index($i));def sgs: [(.SecurityGroups[]?.GroupId),(.NetworkInterfaces[]?.Groups[]?.GroupId)]|map(select(.!=null));([$ins[]|select(isw)|sgs[]]|unique) as $wsg|([$ins[]|select(isw|not)|sgs[]]|unique) as $lsg|($wsg-$lsg-$own) as $wo|([$wids[]|select(. as $i|[$ins[]|select(isw)|.InstanceId]|index($i)|not)]|length) as $wmiss|[.SecurityGroups[]?|select((.GroupId as $id|$own|index($id)) or ([.Tags[]?|select((.Key==("kubernetes.io/cluster/"+$cn)) or (.Value==$cn))]|length>0) or (.GroupId as $id|$lsg|index($id)) or (.GroupId as $id|$wsg|index($id)))] as $g0|[$g0[]|select(.GroupId as $id|$wo|index($id)|not)] as $g|(($g0|length)-($g|length)) as $nwo|((if $nwo>0 then " — \($nwo) security group(s) attached only to Windows nodes NOT assessed" else "" end)+(if $wmiss>0 then " — \($wmiss) Windows node(s) have no instance record, so a security group attached only to them cannot be told apart and IS measured" else "" end)) as $wsx|(if $w>0 then "Linux " else "" end) as $lx| if (($cl.cluster.computeConfig.enabled==true) and $t>0 and $auto==$t and $hy==0) then "all~every \($lx)EC2 node is an EKS Auto Mode node, where SSH and the SSM agent are not available at all, so port 22 cannot reach a listener and break-glass access is the NodeDiagnostic CRD; the open-security-group rule is therefore not applied here — net-2 still measures 0.0.0.0/0 and ::/0 on every other port"+winx($w) elif ($w>0 and ([$nd.items[]?|select(iswin|not)]|length)==0) then winna($w) elif ($g|length)==0 then (if $nwo>0 then "na~NOT ASSESSED — every cluster security group is attached only to Windows nodes" else "na~no cluster SGs" end)+$hysg+winx($w)+$wsx elif ([$g[].IpPermissions[]?|select((.IpProtocol=="-1" or (((((.IpProtocol//"")|tostring|ascii_downcase) as $pr|($pr=="tcp" or $pr=="6"))) and (.FromPort//0)<=22 and (.ToPort//0)>=22)) and (([.IpRanges[]?.CidrIp]|any(.=="0.0.0.0/0")) or ([.Ipv6Ranges[]?.CidrIpv6]|any(.=="::/0"))))]|length)>0 then "none~port 22 reachable from the internet (0.0.0.0/0 or ::/0) on a cluster or Linux node security group"+$hysg+winx($w)+$wsx else "all~no port-22 rule from 0.0.0.0/0 or ::/0 on the cluster and Linux node security groups — prefix-list, peered-VPC and SG-referenced sources were NOT read, and neither was sshd itself"+$hysg+winx($w)+$wsx end'
# sec-31 asks whether control-plane and node security groups are separate. Nothing measures SG separation
# (net-4 measures cluster-SG egress) because AWS states the split is "no longer required and can be
# removed". It stays as `na` with that reason so a reader sees why it is not answered.
m sec-31 cluster '"na~retired: AWS no longer recommends separating control-plane and node security groups"'
# net-1 COUNTS FREE ADDRESSES, WHICH IS NOT THE CONSTRAINT UNDER PREFIX DELEGATION. A /28 needs 16
# CONTIGUOUS addresses:
#   https://docs.aws.amazon.com/eks/latest/userguide/cni-increase-ip-addresses-procedure.html
#   "Even if your subnet has available IP addresses, if the subnet does not have any contiguous `/28`
#   blocks available, you will see the following error in the Amazon VPC CNI plugin for Kubernetes
#   logs. `InsufficientCidrBlocks: ...`"
# A subnet can show hundreds of free addresses and no free /28, and this would still render a green ratio.
# A free-/28 count cannot be derived from what is collected (`describe-subnets` has no per-address detail),
# so the ratio stays a free-address count -- resource_agreement() cross-checks the LEADING `\($ok)/\($t)`
# against the `rl` line -- and the appended clause says what it does not mean. The one collected piece of
# real evidence is reported with it: `Ipv4Prefixes` on an instance network interface
# (API_InstanceNetworkInterface.html), i.e. how many nodes hold a prefix now. net-3 owns the verdict on the mode.
# net-1's `rl` INHERITS THE SCORER'S EMPTY-`subnetIds` FALLBACK, and must keep it: when
# `resourcesVpcConfig.subnetIds` is empty the scorer scopes to EVERY subnet the VPC returned; a list
# intersected against the empty set would publish `0/0` under a verdict computed over N subnets.
rl net-1 subnets cluster instances 'input as $cl|input as $inst|(($cl.cluster.resourcesVpcConfig.subnetIds)//[]) as $own|[.Subnets[]?] as $all|[$all[]|select(($own|length)==0 or (.SubnetId as $id|$own|index($id)))] as $s|[$s[]|select(.AvailableIpAddressCount>=100)] as $p|def n: (.SubnetId//"?")+" ("+((.AvailabilityZone//"?")|tostring)+", "+((.AvailableIpAddressCount//"?")|tostring)+" free IPs)";{pass:[$p[]|n],fail:[($s-$p)[]|n],excluded:(($all|length)-($s|length))}'
m3 net-1 subnets cluster instances 'input as $cl|input as $inst|(($cl.cluster.resourcesVpcConfig.subnetIds)//[]) as $own|[.Subnets[]?|select(($own|length)==0 or (.SubnetId as $id|$own|index($id)))] as $s|($s|length) as $t|([$s[]|select(.AvailableIpAddressCount>=100)]|length) as $ok|[$inst.Reservations[]?.Instances[]?] as $allins|([$allins[]|select((((.Platform//"")|ascii_downcase)=="windows"))]|length) as $wi|[$allins[]|select((((.Platform//"")|ascii_downcase)=="windows")|not)] as $ins|([$ins[].NetworkInterfaces[]?]|length) as $eni|([$ins[]|select([.NetworkInterfaces[]?.Ipv4Prefixes[]?]|length>0)]|length) as $pfx|(if $eni==0 then "" else " — FREE ADDRESSES ARE NOT FREE /28 BLOCKS: where pod IPs come from prefix delegation (the EKS Auto Mode default; opt-in on the VPC CNI) every allocation needs 16 CONTIGUOUS addresses, so a subnet with hundreds of scattered free addresses and no free /28 block has no usable headroom at all, and AWS reports that as InsufficientCidrBlocks. This review does not collect the per-address data a free-/28-block count needs, so the ratio above is an upper bound on headroom rather than a measure of it: \($pfx) of \($ins|length) collected EC2 instance(s) hold an IPv4 delegated prefix on a network interface today, and net-3 reads which allocation mode the Linux nodes are configured for" end) as $pd| if $t==0 then "na~no cluster subnets"+winx($wi) else b($ok;$t)+"~\($ok)/\($t) >=100 IPs (cluster subnets)"+$pd+winx($wi) end'
# net-2 tests the whole port SPAN, not just FromPort. A rule is clean only when it opens exactly one
# world-reachable port that is a plausible public web listener: FromPort==ToPort and (protocol, port) is
# TCP/80, TCP/443 or UDP/443 (QUIC/HTTP-3). FromPort alone would let `80-65535 from 0.0.0.0/0` score CLEAN, and
# a port test alone would let UDP/80 through the 80 carve-out (ICMP/ICMPv6 carry TYPE and CODE in
# FromPort/ToPort). Everything else (UDP/80, other UDP, `-1`, ICMP, ICMPv6, any protocol number not
# rendered as `tcp`/`udp`) is dirty. No renderer-side twin of this test exists; keep it that way.
# net-2's `rl` USES THIS SCORER'S SCOPE AND CLEAN TEST, and must keep both; the `rl` line follows the `m` line:
#   SCOPE: a security group in `resourcesVpcConfig` OR carrying a cluster tag OR attached to a non-Windows
#     node instance in instances.json (the same `$lsg` sec-30 measures). `resourcesVpcConfig` alone would
#     score a tagged-but-unreferenced group and then report it out of scope in the panel that scored it.
#   CLEAN: accepting FromPort and ToPort each in {80,443} would pass `80-443 from 0.0.0.0/0`; this scorer
#     requires FromPort==ToPort.
# The excluded count carries no identifiers, as sec-21: these are OTHER workloads' groups in a possibly
# shared VPC.
rl net-2 sg cluster nodes instances 'input as $cl|input as $nd|input as $inst|[$nd.items[]?|select(iswin and isec2)|((.spec.providerID//"")|split("/")|last)] as $wids|[$inst.Reservations[]?.Instances[]?] as $ins|def isw: (((.Platform//"")|ascii_downcase)=="windows") or (.InstanceId as $i|$wids|index($i));def sgs: [(.SecurityGroups[]?.GroupId),(.NetworkInterfaces[]?.Groups[]?.GroupId)]|map(select(.!=null));([$ins[]|select(isw)|sgs[]]|unique) as $wsg|([$ins[]|select(isw|not)|sgs[]]|unique) as $lsg|([$wids[]|select(. as $i|[$ins[]|select(isw)|.InstanceId]|index($i)|not)]|length) as $wmiss|($cl.cluster.name//"") as $cn|($cl.cluster.resourcesVpcConfig) as $v|((($v.securityGroupIds//[]) + [$v.clusterSecurityGroupId//empty])|unique) as $own|($wsg-$lsg-$own) as $wo|[.SecurityGroups[]?] as $all|[$all[]|select((.GroupId as $id|$own|index($id)) or ([.Tags[]?|select((.Key==("kubernetes.io/cluster/"+$cn)) or (.Value==$cn))]|length>0) or (.GroupId as $id|$lsg|index($id)) or (.GroupId as $id|$wsg|index($id)))] as $g0|[$g0[]|select(.GroupId as $id|$wo|index($id)|not)] as $g|[$g0[]|select(.GroupId as $id|$wo|index($id))] as $gw|[$g[]|select([.IpPermissions[]?|select((([.IpRanges[]?.CidrIp]|any(.=="0.0.0.0/0")) or ([.Ipv6Ranges[]?.CidrIpv6]|any(.=="::/0"))) and (((.IpProtocol//"")|tostring|ascii_downcase) as $pr|((.FromPort//0)) as $fp|($pr!="tcp" and $pr!="udp") or ($fp!=(.ToPort//0)) or (($fp!=443) and (($fp!=80) or ($pr!="tcp")))))]|length==0)] as $p|def n: (.GroupId//"?")+" ("+((.GroupName//"?")|tostring)+")";([$gw[]|n+" — attached only to Windows nodes, NOT measured by this check (this skill supports Linux nodes only)"]+(if $wmiss>0 then ["\($wmiss) Windows node(s) have no instance record, so a security group attached only to them cannot be told apart and IS measured"] else [] end)) as $wc|{pass:[$p[]|n],fail:[($g-$p)[]|n],excluded:(($all|length)-($g0|length))}+(if ($wc|length)>0 then {context:$wc} else {} end)'
m4 net-2 sg cluster nodes instances 'input as $cl|input as $nd|input as $inst|[$nd.items[]?|select(iswin and isec2)|((.spec.providerID//"")|split("/")|last)] as $wids|[$inst.Reservations[]?.Instances[]?] as $ins|def isw: (((.Platform//"")|ascii_downcase)=="windows") or (.InstanceId as $i|$wids|index($i));def sgs: [(.SecurityGroups[]?.GroupId),(.NetworkInterfaces[]?.Groups[]?.GroupId)]|map(select(.!=null));([$ins[]|select(isw)|sgs[]]|unique) as $wsg|([$ins[]|select(isw|not)|sgs[]]|unique) as $lsg|([$wids[]|select(. as $i|[$ins[]|select(isw)|.InstanceId]|index($i)|not)]|length) as $wmiss|($cl.cluster.name//"") as $cn|($cl.cluster.resourcesVpcConfig) as $v|((($v.securityGroupIds//[]) + [$v.clusterSecurityGroupId//empty])|unique) as $own|($wsg-$lsg-$own) as $wo|[.SecurityGroups[]?|select((.GroupId as $id|$own|index($id)) or ([.Tags[]?|select((.Key==("kubernetes.io/cluster/"+$cn)) or (.Value==$cn))]|length>0) or (.GroupId as $id|$lsg|index($id)) or (.GroupId as $id|$wsg|index($id)))] as $g0|[$g0[]|select(.GroupId as $id|$wo|index($id)|not)] as $g|(($g0|length)-($g|length)) as $nwo|((if $nwo>0 then " — \($nwo) security group(s) attached only to Windows nodes NOT assessed (this skill supports Linux nodes only)" else "" end)+(if $wmiss>0 then " — "+"\($wmiss) Windows node(s) have no instance record, so a security group attached only to them cannot be told apart and IS measured" else "" end)) as $wsx|($g|length) as $t|([$g[]|select([.IpPermissions[]?|select((([.IpRanges[]?.CidrIp]|any(.=="0.0.0.0/0")) or ([.Ipv6Ranges[]?.CidrIpv6]|any(.=="::/0"))) and (((.IpProtocol//"")|tostring|ascii_downcase) as $pr|((.FromPort//0)) as $fp|($pr!="tcp" and $pr!="udp") or ($fp!=(.ToPort//0)) or (($fp!=443) and (($fp!=80) or ($pr!="tcp")))))]|length==0)]|length) as $ok| if $t==0 then (if $nwo>0 then "na~NOT ASSESSED — every cluster security group is attached only to Windows nodes" else "na~no cluster SGs" end)+$wsx else b($ok;$t)+"~\($ok)/\($t) cluster and Linux node SGs carry no 0.0.0.0/0 or ::/0 inbound rule outside TCP 80/443 and UDP 443 — prefix lists, peered CIDRs and SG-referenced sources are NOT resolved"+$wsx end'
# ECR supply-chain controls (scan-on-push, tag immutability): a supply-chain exposure, not an overspend;
# the EKS Best Practices Guides place both under Security / Image Security.
# BOTH READ `initContainers` AS WELL AS `containers`: an ECR repository seen only in an init container would
# otherwise be invisible.
# THE `na` SAYS WHAT WAS NOT EXAMINED, because "no cluster ECR repos" is usually false. The match is the full
# `.repositoryUri` (`<registry account>.dkr.ecr.<region>.amazonaws.com/<name>`) against the image reference
# with tag and digest stripped (a `dkr.ecr-fips` reference reads as the same registry), over THIS account's
# `describe-repositories` in the collected Region. Matching the NAME alone would give an image from another
# account or Region the settings of a same-named local repository. A cluster whose ECR images all come from a
# DIFFERENT account gets an empty intersection and the topic leaves the score (`na` is excluded from
# numerator and denominator); the detail names the gap instead.
m2 lens-12 ecr pods 'input as $p|[$p.items[]|(.spec.containers[]?,.spec.initContainers[]?)|.image|select(test("dkr.ecr"))|sub("\\.dkr\\.ecr-fips\\.";".dkr.ecr.")|capture("^(?<u>[^/]*\\.dkr\\.ecr\\.[^/]*/[^:@]+)").u] as $used|($used|unique|length) as $nu|([.repositories[]?]|length) as $nrepo|[.repositories[]?|select((.repositoryUri//"") as $ru|$used|index($ru))] as $r|($r|length) as $t|([$r[]|select(.imageScanningConfiguration.scanOnPush==true)]|length) as $ok| if $t==0 then "na~NOT ASSESSED, AND NOT A PASS: none of the \($nrepo) ECR repository/ies this account returns in this Region is the repository of any of the \($nu) distinct ECR image(s) the cluster pulls, so scan-on-push was never examined for a single image. This question matches the full repository URI (registry account, Region and name) against the repositories of THIS account in THIS Region only, so an image pulled from an ECR registry in another account or Region — the shared-registry, replicated-repository and AWS-add-on case — is not examined even when a repository of the same name exists here, and neither is any non-ECR registry" else "na~NOT ASSESSED, AND NOT A PASS: the cluster pulls images from \($t) ECR repository/ies of this account and Region, and the repository-level scanOnPush flag is set on \($ok) of them, but that flag does not show whether an image is scanned. AWS has deprecated repository-level scan-on-push in favour of the registry-level scanning configuration, and that configuration decides: under enhanced scanning a repository that matches no registry filter is not scanned whatever its flag says, and one that matches is scanned with the flag off. This review does not read the registry-level scanning configuration, so whether these images are scanned was not assessed" end'
m2 lens-13 ecr pods 'input as $p|[$p.items[]|(.spec.containers[]?,.spec.initContainers[]?)|.image|select(test("dkr.ecr"))|sub("\\.dkr\\.ecr-fips\\.";".dkr.ecr.")|capture("^(?<u>[^/]*\\.dkr\\.ecr\\.[^/]*/[^:@]+)").u] as $used|($used|unique|length) as $nu|([.repositories[]?]|length) as $nrepo|[.repositories[]?|select((.repositoryUri//"") as $ru|$used|index($ru))] as $r|($r|length) as $t|([$r[]|select(.imageTagMutability=="IMMUTABLE")]|length) as $ok| if $t==0 then "na~NOT ASSESSED, AND NOT A PASS: none of the \($nrepo) ECR repository/ies this account returns in this Region is the repository of any of the \($nu) distinct ECR image(s) the cluster pulls, so tag immutability was never examined for a single image. This question matches the full repository URI (registry account, Region and name) against the repositories of THIS account in THIS Region only, so an image pulled from an ECR registry in another account or Region — the shared-registry, replicated-repository and AWS-add-on case — is not examined even when a repository of the same name exists here, and neither is any non-ECR registry" else b($ok;$t)+"~\($ok)/\($t) immutable" end'
# net-3 does NOT answer `na~auto mode fully manages the VPC CNI; prefix delegation is not configurable` on a
# `computeConfig.enabled` cluster: prefix delegation is the documented Auto Mode DEFAULT
#   https://docs.aws.amazon.com/eks/latest/userguide/auto-networking.html
#   "EKS Auto Mode defaults to using prefix delegation (/28 prefixes) for pod networking and maintains a
#   predefined warm pool of IP resources that scales based on the number of scheduled pods"
# and it IS configurable:
#   https://docs.aws.amazon.com/eks/latest/userguide/create-node-class.html
#   "ipv4PrefixSize is default to Auto which is prefix and fallback to secondary IP. \"32\" is the
#   secondary IP mode."
# Only the field `spec.advancedNetworking.ipv4PrefixSize` is read. A NodeClass that opts into secondary-IP
# mode is reported, not credited, and only a NodeClass that a collected node was launched from counts (label
# `eks.amazonaws.com/nodeclass`): the setting applies only to nodes from that class.
# THE GATE IS EVERY EC2 NODE, NOT `computeConfig.enabled`. On a mixed-mode cluster a flag-based `na` would
# suppress a real finding (the identical Standard cluster answers `none~off`; `na` is excluded from scoring)
# although an `aws-node` DaemonSet with `ENABLE_PREFIX_DELEGATION` in its env still runs. Auto Mode
# capabilities do not reach non-Auto-Mode nodes (eks-add-ons.html: "if your cluster combines Auto mode with
# other compute options ... these add-ons remain necessary"). Same membership test, $t>0 and Fargate
# exclusion as lens-2, sec-30 and sec-21: CHANGE ONE, CHANGE ALL.
# `none` for an `ipv4PrefixSize: "32"` NodeClass is the accurate answer to "is prefix delegation enabled" and
# NOT automatically a defect (create-node-class.html recommends secondary IP mode for pod-sparse workloads),
# so the remediation prose tells the reader to check the opt-out was deliberate. Low severity.
# `$v` is read as `[...]|first`, NOT bound from a streaming path: binding `as $v` to an expression that yields
# ZERO outputs (no ENABLE_PREFIX_DELEGATION env var, or no aws-node) makes the whole program emit nothing and
# trips the helper's "produced no output" abort. `first` over a list always yields one value, null included
# (the same idiom sec-4 uses for $mode).
# THE VERDICT READS ACTUAL ALLOCATION STATE, NOT ONLY CONFIGURATION (as sec-4). An Auto Mode cluster configured
# for prefix delegation can have nodes not using it when subnets are too fragmented for a contiguous /28
# (the CNI falls back to secondary IP). `describe-instances` already reports it per interface:
#   https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_InstanceNetworkInterface.html
#   "Ipv4PrefixSet.N -- The IPv4 delegated prefixes that are assigned to the network interface."
# (`Ipv4Prefixes` in the JSON shape, `Required: No`), so an interface with no entry has no delegated prefix.
# ABSENCE IS ONLY READ WHERE THERE IS INTERFACE DATA: with zero collected interfaces the question falls back to
# the configuration answer and SAYS it was not verified ("no prefixes found" is not "no interfaces looked at").
# LINUX NODES ONLY. Windows nodes (`iswin`) and Windows instances (`.Platform == "windows"`) leave the sets;
# the detail names how many Windows nodes were not assessed (`winx`), and a cluster whose EC2 nodes are all
# Windows answers `na` (`winna`) before the hybrid and Fargate arms. THE AUTO MODE ARM IS NOT GATED ON THE
# WINDOWS COUNT: its verdict comes from the Linux instances' allocation state (or says CONFIGURATION ONLY),
# so Windows nodes change its wording, not its answer. Gating it would judge Auto Mode nodes by the aws-node
# env, which does not configure them.
m6 net-3 daemonsets nodes cluster nodeclasses instances vpccniconfig 'input as $n|input as $cl|input as $nc|input as $inst|input as $cm|[$n.items[]?|select(islinux)] as $ec2|([$n.items[]?|select(iswin and isec2)]|length) as $w|([$n.items[]?|select(ishy)]|length) as $hy|($ec2|length) as $t|([$ec2[]|select((.metadata.labels["eks.amazonaws.com/compute-type"]//"")=="auto")]|length) as $auto|(if $w>0 then "Linux " else "" end) as $lx|([$ec2[]|.metadata.labels["eks.amazonaws.com/nodeclass"]//empty]|unique) as $ncu|[$nc.items[]?|select((((.spec.advancedNetworking.ipv4PrefixSize)//"")|tostring)=="32")|select(.metadata.name as $m|$ncu|index($m))|.metadata.name] as $off|[$inst.Reservations[]?.Instances[]?|select((((.Platform//"")|ascii_downcase)=="windows")|not)] as $ins|($ins|length) as $ni|([$ins[].NetworkInterfaces[]?]|length) as $eni|([$ins[]|select([.NetworkInterfaces[]?.Ipv4Prefixes[]?]|length>0)]|length) as $pfx|([.items[]?|select((.metadata.name=="aws-node" and (.metadata.namespace//"")=="kube-system"))|.spec.template.spec.containers[]?.env[]?|select(.name=="ENABLE_PREFIX_DELEGATION")|.value]|first) as $v|("\($t) Linux node(s): ENABLE_PREFIX_DELEGATION on the aws-node DaemonSet is "+(if $v==null then "not set" else "\($v)" end)) as $cfg|(if $v=="true" then 1 else 0 end) as $on|(if $auto>0 and $auto<$t then " (\($auto) of \($t) EC2 nodes are EKS Auto Mode nodes and take prefix delegation from the Auto Mode default; the remaining \($t - $auto) take their pod IP mode from the setting(s) named here)" else "" end) as $mix| if (($cl.cluster.computeConfig.enabled==true) and $t>0 and $auto==$t) then (if ($off|length)>0 then "none~every \($lx)EC2 node is an EKS Auto Mode node, but NodeClass \($off|join(", ")) sets advancedNetworking.ipv4PrefixSize to 32 (secondary IP mode), which is prefix delegation turned off" + (if $eni>0 then " — \($pfx) of \($ni) collected instance(s) hold an IPv4 delegated prefix" else "" end) elif $eni==0 then "all~every \($lx)EC2 node is an EKS Auto Mode node and Auto Mode defaults to prefix delegation (/28 prefixes) for pod networking; no NodeClass that a collected node uses (its eks.amazonaws.com/nodeclass label) sets advancedNetworking.ipv4PrefixSize to 32 (secondary IP mode) — CONFIGURATION ONLY: no EC2 network-interface data was collected, so whether a prefix was actually allocated is NOT VERIFIED" else b($pfx;$ni)+"~every \($lx)EC2 node is an EKS Auto Mode node and no NodeClass that a collected node uses (its eks.amazonaws.com/nodeclass label) sets advancedNetworking.ipv4PrefixSize to 32, so prefix delegation is the configured mode, and \($pfx) of \($ni) collected instance(s) hold an IPv4 delegated prefix on a network interface"+(if $pfx<$ni then " — the other \($ni - $pfx) are allocating individual secondary IPs, the documented fallback when no contiguous /28 block is free in the subnet, so the documented default is NOT what this cluster is doing (net-1 counts free addresses, not free /28 blocks)" else ", which confirms the default in the allocation state rather than assuming it" end)+hyx($hy) end)+winx($w) elif ($t==0 and $w>0) then winna($w)+hyx($hy) elif ($t==0 and $hy>0) then hyna($hy;"ENABLE_PREFIX_DELEGATION changes how the Amazon VPC CNI allocates Pod IPs from ENI prefixes, and AWS documents that the VPC CNI is not compatible with hybrid nodes and gives its aws-node DaemonSet anti-affinity for eks.amazonaws.com/compute-type=hybrid, so there is no prefix delegation here to turn on")+winx($w) elif $t==0 then "na~fargate"+winx($w) else (if $eni==0 then b($on;1) else b($pfx;$ni) end)+"~"+$cfg+$mix+(if $eni==0 then " — CONFIGURATION ONLY: no EC2 network-interface data was collected, so actual allocation is NOT VERIFIED" else " — \($pfx) of \($ni) collected instance(s) hold an IPv4 delegated prefix on a network interface"+(if ($on>0 and $pfx==0) then ": configured on but not in use, which is the InsufficientCidrBlocks symptom of a subnet with no free contiguous /28 block" elif ($on==0 and $pfx>0) then ", which contradicts the setting(s) above — one of them may have changed after the nodes launched" else "" end) end)+hyx($hy)+winx($w) end'
# net-4 does NOT ask whether "separate SGs" are used by testing that resourcesVpcConfig.securityGroupIds
# contains clusterSecurityGroupId. AWS: the cluster security group "is applied by default to the Kubernetes
# control plane ... as well as any managed compute resources created by Amazon EKS. ADDITIONAL cluster
# security groups control communications from the Kubernetes control plane to compute resources." It spans
# BOTH planes by design and is never in the additional list, so that check would report "separate SGs" on
# nearly every cluster. AWS also says the split is "no longer required and can be removed".
# What remains measurable is whether the cluster SG's default allow-ALL egress was narrowed ("Optionally, users
# can remove this egress rule and limit the open ports between the cluster and nodes"). `na` when the cluster
# SG cannot be identified: absent data is not a finding.
# net-4 catches ANY rule opening every port to the world, not only the literal `IpProtocol: "-1"` EKS creates:
# `tcp 0-65535 -> 0.0.0.0/0` is an identical grant. net-4's `rl` USES THIS SCORER'S WIDER TEST: a
# literal-`-1`-only test would list the `tcp 0-65535` rule as "narrowed" under the scorer's `none`. The two
# `na` arms emit `context` ONLY (empty `pass`/`fail`): a rule that never ran must not label anything as
# having passed it.
rl net-4 sg cluster 'input as $cl|($cl.cluster.resourcesVpcConfig.clusterSecurityGroupId//"") as $csg|[.SecurityGroups[]?|select(.GroupId==$csg)] as $g| if ($csg|length)==0 then {pass:[],fail:[],kind:"field",context:["no clusterSecurityGroupId on this cluster"]} elif ($g|length)==0 then {pass:[],fail:[],kind:"field",context:[$csg+" (not present in the collected security groups)"]} else ([$g[]|(.GroupId//"?") as $gid|.IpPermissionsEgress[]?|{open:(((([.IpRanges[]?.CidrIp]|index("0.0.0.0/0"))!=null) or (([.Ipv6Ranges[]?.CidrIpv6]|index("::/0"))!=null)) and (.IpProtocol=="-1" or ((.FromPort//0)<=1 and (.ToPort//0)>=65535))),dflt:(.IpProtocol=="-1"),d:($gid+" egress "+(if .IpProtocol=="-1" then "ALL protocols" else (.IpProtocol|tostring) end)+" -> "+((([.IpRanges[]?.CidrIp,.Ipv6Ranges[]?.CidrIpv6]|map(select((.!=null) and (.!="")))|join(", ")))|if .=="" then "security group / prefix list" else . end))}]) as $r|{pass:[$r[]|select(.open|not)|.d],fail:[$r[]|select(.open)|(.d+(if .dflt then "   <- the default rule this check looks for" else "   <- opens every port to the world, the same grant as the default rule" end))],kind:"field"} end'
m2 net-4 sg cluster 'input as $cl|($cl.cluster.resourcesVpcConfig.clusterSecurityGroupId//"") as $csg|([.SecurityGroups[]?|select(.GroupId==$csg)]|first) as $g| if ($csg|length)==0 then "na~no cluster security group" elif $g==null then "na~cluster SG not in the collected security groups" elif ([$g.IpPermissionsEgress[]?|select(((([.IpRanges[]?.CidrIp]|index("0.0.0.0/0"))!=null) or (([.Ipv6Ranges[]?.CidrIpv6]|index("::/0"))!=null)) and (.IpProtocol=="-1" or ((.FromPort//0)<=1 and (.ToPort//0)>=65535)))]|length)>0 then "none~cluster SG \($csg) still allows ALL egress to 0.0.0.0/0 or ::/0 (EKS default)" else "all~cluster SG \($csg) egress is narrowed to something other than 0.0.0.0/0 and ::/0 — prefix-list and SG-referenced destinations are NOT resolved" end'

# ── workload-security (16) ──
m3 sec-10 validatingwebhooks mutatingwebhooks addons 'input as $mw|input as $ad|[$ad.addonDetails[]?|select(.marketplaceInformation==null)|{a:(.addonName//"?"),s:(.namespaceConfig.namespace//"")}|select(.s!="" and .s!="kube-system")] as $ans|[(.items[]?|{k:"validating",o:.}),($mw.items[]?|{k:"mutating",o:.})|select((.o.metadata.name|test("aws-load-balancer|vpc-resource|pod-identity|^eks-|amazon-"))|not)] as $nw|[$nw[]|((.o.webhooks//[])|map((.clientConfig.service.namespace//"") as $s|[$ans[]|select(.s==$s)|.a]|first)) as $t|(($t|length)>0 and ($t|all(.[]; .!=null))) as $tied|.+{t:$tied,a:(if $tied then ($t|unique|join("+")) else "" end)}] as $nt|[$nt[]|select(.t)|"\(.k) \(.o.metadata.name) (add-on \(.a))"] as $x|[$nt[]|select(.t|not)|.+{p:((.k=="validating") and ([.o.webhooks[]?|.rules[]?|select(((.scope//"*")!="Cluster") and ([.apiGroups[]?]|any(.=="" or .=="*")) and ([.resources[]?]|any(.=="pods" or .=="*" or .=="*/*")) and ([.operations[]?]|any(.=="CREATE" or .=="*")))]|length>0))}] as $u|[$u[]|select(.p)|.o.metadata.name] as $pn|[$u[]|select(.p|not)|"\(.k) \(.o.metadata.name)"] as $on|(if ($on|length)>0 then "; \($on|length) other non-AWS webhook configuration(s) not counted, because none of their webhooks is a validating webhook whose rules match Pod CREATE: "+($on|join(", ")) else "" end) as $os|(if ($x|length)>0 then "; \($x|length) webhook configuration(s) left out as EKS add-on webhooks, because every webhook in each calls a Service in the namespace of an installed EKS add-on that is not an AWS Marketplace add-on: "+($x|join(", ")) else "" end) as $xs| if ($pn|length)>0 then "all~\($pn|length) non-AWS validating webhook configuration(s) whose rules match Pod CREATE: "+($pn|join(", "))+$os+$xs elif ($on|length)>0 then "none~no non-AWS validating webhook whose rules match Pod CREATE"+$os+$xs else "none~only webhooks installed by AWS or by EKS add-ons"+$xs end'
# sec-11 reads the enforce LEVEL, not the presence of a `pod-security.kubernetes.io/` label: matching the
# prefix would let `enforce: privileged` (which opts OUT of restriction) score `all`. Only `restricted` and
# `baseline` are enforcement; `warn`/`audit` do not gate admission, so only the `enforce` key counts.
# `context` is the namespaces the `^(kube-|amazon-)` filter removed, published so a partial verdict cannot
# read as whole-cluster, and counted on neither side.
rl sec-11 namespaces '[.items[]|select(.metadata.name|test("^(kube-|amazon-)")|not)] as $ns|[$ns[]|select((.metadata.labels//{})|to_entries|any((.key|test("^pod-security.kubernetes.io/enforce$")) and (.value=="restricted" or .value=="baseline")))] as $p|{pass:[$p[]|(.metadata.name//"?")],fail:[($ns-$p)[]|(.metadata.name//"?")],context:[.items[]|select(.metadata.name|test("^(kube-|amazon-)"))|(.metadata.name//"?")]}'
m2 sec-11 namespaces pods 'input as $p|[.items[]|select(.metadata.name|test("^(kube-|amazon-)")|not)] as $ns|($ns|length) as $t|([$ns[]|select((.metadata.labels//{})|to_entries|any((.key|test("^pod-security.kubernetes.io/enforce$")) and (.value=="restricted" or .value=="baseline")))]|length) as $ok| if $t==0 then "na~no workload namespaces" else b($ok;$t)+"~\($ok)/\($t) ns enforce restricted|baseline" end'
# ── THE FOUR POLICY-ENGINE QUESTIONS SCORE ON WHAT IS LOADED, NOT ON WHAT IS ENFORCED ──
# sec-16, adm-1, adm-2 and adm-3 read the SAME three files (kyverno, constraints, constrainttemplates) and
# share ONE state rule, keyed on `$P>0 or $tmpl>0`, so the four cannot disagree; a difference between them
# anywhere is drift. With $P = (all Kyverno policies) + (all Gatekeeper Constraints), $tmpl = ConstraintTemplates:
#   $P>0               -> all   policies are loaded, the only engine evidence these files give
#   $P==0 and $tmpl>0  -> none  a ConstraintTemplate is a schema; without a Constraint nothing is evaluated
#   $P==0 and $tmpl==0 -> none  nothing in these files (engine absent, OR present and empty)
# Do NOT turn any of these four into `na` on the empty arm: `na` drops a question from the pillar
# denominator while `none` stays in as a counted Fail, so `na` would make the scale NON-MONOTONIC (a
# templates-only cluster with four counted Fails would score LOWER than an engine-free one whose questions
# read `na`: installing a policy engine would lower the score). With `none` in both shapes they tie.
# THE THRESHOLD IS WHAT THE COLLECTION SHOWS, NOT WHAT IS RUNNING: Kyverno deployed and healthy with zero
# ClusterPolicies, no Constraints and no ConstraintTemplates writes nothing into these files, so it is
# indistinguishable from no engine, and no arm here reads deployments.json. Do NOT describe the boundary as
# "engine present". All four open the arm's detail `no policy engine detected` (not "installed") and go on to
# name what was seen -- no Kyverno ClusterPolicy, no Gatekeeper Constraint, no ConstraintTemplate -- and to
# say an engine holding nothing writes the same empty files.
# THE KYVERNO CLAUSE NAMES THE KIND: collect.sh queries `clusterpolicies.kyverno.io` and nothing else, so
# an install whose rules are namespaced `Policy` objects writes the same empty kyverno.json as no Kyverno.
# All four also carry `$kyns`, which states that gap in the reader's terms; it is appended to ALL THREE arms
# (the `$P>0` count is short by the same objects), hence the parenthesised conditional. If
# `policies.kyverno.io` is ever collected, `$kyns` comes out of all four in the same edit.
# ENFORCEMENT IS NOT RESOLVED FOR PUBLICATION BY ANY OF THE FOUR (see the PE note at the top): with at least
# one policy each appends the SAME sentence, opening `SCORED ON DEPLOYMENT ONLY` and closing `it does NOT
# assert that anything is refused at admission`. A fifth question that starts scoring deployment has to
# copy the string.
# WHY adm-2'S COUNT IS SPELLED `N of M`, AND WHY NO DETAIL HERE OPENS WITH `n/m`: reduce.sh runs a
# state<->ratio gate over each measured record whose detail matches `^[0-9]+/[0-9]+` (every id bar those
# in RATIO_STATE_EXEMPT), requiring state==b(n;t). A detail leading with `\($kyok+$gcok)/\($ky+$gc) ...`
# would pair state `all` with a leading `0/3` and be refused. adm-2's `\($kok) of \($ky)` privileged
# disclosure is the only ratio in the four, is spelled in words and sits after the deployment fact, so it
# satisfies the gate with NO exemption: do not add these to RATIO_STATE_EXEMPT or weaken the gate. adm-1
# opens with a bare count (`\($P) admission policy/ies deployed`), which the gate ignores because a lone
# integer is not `n/m`; a slash and a second number after it would arm the gate.
m3 sec-16 kyverno constraints constrainttemplates 'input as $c|input as $ct|([.items[]?]|length) as $ky|([$c.items[]?]|length) as $gc|([$ct.items[]?]|length) as $tmpl|($ky+$gc) as $P|(" — SCORED ON DEPLOYMENT ONLY. This verdict says a policy engine is deployed and carrying policies; it does NOT assert that anything is refused at admission.") as $disc|(" — collection gap: only cluster-scoped Kyverno ClusterPolicy is read here, not namespaced Kyverno Policy objects, so rules a Kyverno install keeps in namespaced Policy objects contribute nothing to this verdict. Collecting them is planned for a future version.") as $kyns|(if $P>0 then "all~policy engine deployed with \($P) policy/ies loaded (\($ky) Kyverno, \($gc) Gatekeeper Constraint(s))"+$disc+" — Pod Security Standards namespace labels are NOT read here (sec-11 scores those), and which Pod fields the policies cover is not inspected" elif $tmpl>0 then "none~policy engine deployed but zero policies loaded: \($tmpl) Gatekeeper ConstraintTemplate(s) are schemas, and without Constraint objects nothing is evaluated at admission" else "none~no policy engine detected: the collected data holds no Kyverno ClusterPolicy, no Gatekeeper Constraint and no ConstraintTemplate — an engine installed with nothing loaded writes the same empty files, so it reads identically here" end)+$kyns'
# adm-1 counts POLICY OBJECTS, and a Gatekeeper ConstraintTemplate is not one: templates with zero
# Constraints would score `all` on a cluster evaluating nothing. Presence decides the state; the
# 5-to-10 target appears only in the depth disclosure and scores nothing.
m3 adm-1 kyverno constraints constrainttemplates 'input as $c|input as $ct|([.items[]?]|length) as $ky|([$c.items[]?]|length) as $gc|([$ct.items[]?]|length) as $tmpl|($ky+$gc) as $P|(" — SCORED ON DEPLOYMENT ONLY. This verdict says a policy engine is deployed and carrying policies; it does NOT assert that anything is refused at admission.") as $disc|(" — collection gap: only cluster-scoped Kyverno ClusterPolicy is read here, not namespaced Kyverno Policy objects, so rules a Kyverno install keeps in namespaced Policy objects contribute nothing to this verdict. Collecting them is planned for a future version.") as $kyns|(if $P>0 then "all~\($P) admission policy/ies deployed (\($ky) Kyverno, \($gc) Gatekeeper Constraint(s))"+$disc+" — coverage depth is reported here, not scored: this counts policy objects, not which Pod fields or workload kinds they cover, so one policy and twenty score alike; 5 to 10 policies covering the baseline Pod Security controls remains the remediation target, and it does not drive this state" elif $tmpl>0 then "none~policy engine deployed but zero policies loaded: \($tmpl) Gatekeeper ConstraintTemplate(s) are schemas, and without Constraint objects nothing is evaluated at admission" else "none~no policy engine detected: the collected data holds no Kyverno ClusterPolicy, no Gatekeeper Constraint and no ConstraintTemplate — an engine installed with nothing loaded writes the same empty files, so it reads identically here" end)+$kyns'
# adm-2 judges what a policy DOES, not what it is called: a "privileg" substring match on the name would score
# a policy named `allow-privileged-for-ci` (which PERMITS privileged pods) as blocking them. `kypriv` resolves
# one Kyverno rule that BOTH resolves to Enforce AND requires privileged==false, and feeds adm-2's privileged
# DISCLOSURE, not its state. The caveat on which `validate` forms are read (a reader who wrote
# `validate.podSecurity` must be told it reads as absent) stays attached to that disclosure.
m3 adm-2 kyverno constraints constrainttemplates 'input as $c|input as $ct|([.items[]?]|length) as $ky|([$c.items[]?]|length) as $gc|([$ct.items[]?]|length) as $tmpl|($ky+$gc) as $P|([.items[]?|select(kypriv)]|length) as $kok|([.items[]?|select(kynsov)]|length) as $nsov|(if $nsov>0 then " — \($nsov) Kyverno policy/ies carry a failureAction override this cannot evaluate (a namespace list, or a namespaceSelector): it is scoped to namespaces this cannot resolve — a namespace list, or a label selector — where the action differs from the one counted here" else "" end) as $ovnote|([.items[]?|select(kyver18)]|length) as $kyn|(if $kyn>0 then " — this verdict is the release-1.19-and-later admission behaviour, and at least one supported Kyverno release resolves this policy differently: every release before 1.19 applies ONE action policy-wide, taken from the first rule that sets one, and releases before 1.18 additionally ignore a failureAction override that names neither namespaces nor a namespaceSelector, and read only the first verifyImages entry. Which of those applies depends on the release you run, so this verdict may over- or under-state enforcement there" else "" end) as $kyver|(" — SCORED ON DEPLOYMENT ONLY. This verdict says a policy engine is deployed and carrying policies; it does NOT assert that anything is refused at admission.") as $disc|(" — collection gap: only cluster-scoped Kyverno ClusterPolicy is read here, not namespaced Kyverno Policy objects, so rules a Kyverno install keeps in namespaced Policy objects contribute nothing to this verdict. Collecting them is planned for a future version.") as $kyns|(if $P>0 then "all~policy engine deployed with \($P) policy/ies loaded"+$disc+" — privileged is reported here, not scored: \($kok) of \($ky) Kyverno policy/ies demonstrably carry a privileged: false requirement inside a rule that resolves to Enforce, and the Pod field a Gatekeeper Constraint covers is NOT inspected, so the \($gc) Gatekeeper Constraint(s) are neither credited nor discounted here"+" — the privileged check reads validate.pattern and validate.anyPattern, including Kyverno key anchors, a string \"false\" and the \"!true\" not-equal form, over the containers list and the Pod, template and CronJob jobTemplate nestings; a bare key or an =() Equality anchor imposes a requirement while a () Condition anchor only selects, so (privileged) restricts nothing; the MAIN containers list must carry the requirement, since a pattern constraining only initContainers or ephemeralContainers admits a privileged main container; when validate.pattern is set it is used ALONE, because upstream never evaluates anyPattern beside it; for anyPattern alone it requires EVERY alternative to restrict privileged, because one permissive alternative admits the Pod; and it does NOT read validate.deny, validate.cel, validate.podSecurity, validate.foreach, validate.assert or validate.manifests -- podSecurity being the modern canonical way to disallow privileged containers, so a cluster using it will read as absent here -- a policy using those forms will read as absent here"+$ovnote+$kyver elif $tmpl>0 then "none~policy engine deployed but zero policies loaded: \($tmpl) Gatekeeper ConstraintTemplate(s) are schemas, and without Constraint objects nothing restricts a privileged pod"+$ovnote+$kyver else "none~no policy engine detected: the collected data holds no Kyverno ClusterPolicy, no Gatekeeper Constraint and no ConstraintTemplate — an engine installed with nothing loaded writes the same empty files, so it reads identically here"+$ovnote+$kyver end)+$kyns'
m3 adm-3 kyverno constraints constrainttemplates 'input as $gk|input as $ct|([.items[]?]|length) as $ky|([$gk.items[]?]|length) as $gc|([$ct.items[]?]|length) as $tmpl|($ky+$gc) as $P|(" — SCORED ON DEPLOYMENT ONLY. This verdict says a policy engine is deployed and carrying policies; it does NOT assert that anything is refused at admission.") as $disc|(" — collection gap: only cluster-scoped Kyverno ClusterPolicy is read here, not namespaced Kyverno Policy objects, so rules a Kyverno install keeps in namespaced Policy objects contribute nothing to this verdict. Collecting them is planned for a future version.") as $kyns|(if $P>0 then "all~policy engine deployed with \($P) policy/ies loaded"+$disc elif $tmpl>0 then "none~policy engine deployed but zero policies loaded: \($tmpl) Gatekeeper ConstraintTemplate(s) are schemas, and without Constraint objects nothing is evaluated at admission" else "none~no policy engine detected: the collected data holds no Kyverno ClusterPolicy, no Gatekeeper Constraint and no ConstraintTemplate — an engine installed with nothing loaded writes the same empty files, so it reads identically here" end)+$kyns'
# ── THE SIX FLATTENERS: sec-12, sec-15, podsec-1, podsec-2, podsec-3, podsec-5 ──
# Each `m` program binds its container list with NO pod and NO namespace (a COUNT does not need them). A NAME
# does, so every `rl` line here binds the pod's `namespace/name` BEFORE descending into containers and emits
# `<namespace>/<pod> / <container>`; a bare `app` names nothing an operator can look at. `podsec-3` is the
# one pod-level member and names pods only.
# THE SELECTION IS COPIED FROM THE `m` LINE CLAUSE FOR CLAUSE. `fail` is `$all - $pass` in all six so the
# test appears once per question and cannot drift against its complement.
rl sec-12 pods daemonsets '(input|winds) as $wds|[.items[]|select((.metadata.namespace//"")|test("^(kube-|amazon-)")|not)|select((.status.phase//"")|IN("Succeeded","Failed")|not)] as $wl|[$wl[]|select(iswinpod($wds))|((.metadata.namespace//"")+"/"+(.metadata.name//"?"))] as $wn|($wn|length) as $wp|[$wl[]|select(iswinpod($wds)|not)] as $lw|[$lw[]|((.metadata.namespace//"")+"/"+(.metadata.name//"?")) as $pn|.spec.containers[]?|{n:($pn+" / "+(.name//"?")),c:.}] as $c|[$c[]|select((((.c.image//"")|test(":latest$")) or (((.c.image//"")|test("@sha256:|:[^/]+$"))|not))|not)] as $p|if ($lw|length)==0 and $wp>0 then {pass:[],fail:[],context:(["\($wp) Windows pod(s) not assessed — this skill supports Linux nodes only"]+$wn),context_only:true} else {pass:[$p[]|.n],fail:[($c-$p)[]|.n]}+(if $wp>0 then {context:(["\($wp) Windows pod(s) not assessed — this skill supports Linux nodes only"]+$wn)} else {} end) end'
m2 sec-12 pods daemonsets '(input|winds) as $wds|[.items[]|select((.metadata.namespace//"")|test("^(kube-|amazon-)")|not)|select((.status.phase//"")|IN("Succeeded","Failed")|not)] as $wl|([$wl[]|select(iswinpod($wds))]|length) as $wp|[$wl[]|select(iswinpod($wds)|not)] as $lw|[$lw[]|.spec.containers[]?] as $c|($c|length) as $t|([$c[]|select(((.image//"")|test(":latest$")) or (((.image//"")|test("@sha256:|:[^/]+$"))|not))]|length) as $bad| if ($lw|length)==0 and $wp>0 then winpna($wp) elif $t==0 then "na~no workload containers"+winpx($wp) else b(($t-$bad);$t)+"~\(($t-$bad))/\($t) workload containers carry a digest or an explicit tag other than :latest -- which is what is measured, NOT immutability: only an @sha256: digest is immutable, and a plain tag such as :stable passes here yet can still be re-pointed (initContainers and ephemeral containers are not in this denominator)"+winpx($wp) end'
rl sec-15 pods daemonsets '(input|winds) as $wds|[.items[]|select((.metadata.namespace//"")|test("^(kube-|amazon-)")|not)|select((.status.phase//"")|IN("Succeeded","Failed")|not)] as $wl|[$wl[]|select(iswinpod($wds))|((.metadata.namespace//"")+"/"+(.metadata.name//"?"))] as $wn|($wn|length) as $wp|[$wl[]|select(iswinpod($wds)|not)] as $lw|[$lw[]|((.metadata.namespace//"")+"/"+(.metadata.name//"?")) as $pn|.spec.securityContext as $ps|.spec.containers[]?|{n:($pn+" / "+(.name//"?")),sc:.securityContext,ps:$ps}] as $c|[$c[]|select(((if (.sc.runAsNonRoot != null) then .sc.runAsNonRoot else .ps.runAsNonRoot end)==true) or .sc.readOnlyRootFilesystem==true or .sc.allowPrivilegeEscalation==false)] as $p|if ($lw|length)==0 and $wp>0 then {pass:[],fail:[],context:(["\($wp) Windows pod(s) not assessed — this skill supports Linux nodes only"]+$wn),context_only:true} else {pass:[$p[]|.n],fail:[($c-$p)[]|.n]}+(if $wp>0 then {context:(["\($wp) Windows pod(s) not assessed — this skill supports Linux nodes only"]+$wn)} else {} end) end'
m2 sec-15 pods daemonsets '(input|winds) as $wds|[.items[]|select((.metadata.namespace//"")|test("^(kube-|amazon-)")|not)|select((.status.phase//"")|IN("Succeeded","Failed")|not)] as $wl|([$wl[]|select(iswinpod($wds))]|length) as $wp|[$wl[]|select(iswinpod($wds)|not)] as $lw|[$lw[]|.spec.securityContext as $ps|.spec.containers[]?|{sc:.securityContext,ps:$ps}] as $c|($c|length) as $t|([$c[]|select(((if (.sc.runAsNonRoot != null) then .sc.runAsNonRoot else .ps.runAsNonRoot end)==true) or .sc.readOnlyRootFilesystem==true or .sc.allowPrivilegeEscalation==false)]|length) as $ok| if ($lw|length)==0 and $wp>0 then winpna($wp) else b($ok;$t)+"~\($ok)/\($t) secctx (workloads)"+winpx($wp) end'
# `podsec-1`, `podsec-2`, `podsec-4` and `podsec-5` TAKE THEIR DENOMINATOR FROM
# `(.spec.containers[]?,.spec.initContainers[]?,.spec.ephemeralContainers[]?)`; `lens-12`/`lens-13` read the
# first two. `.spec.containers[]?` alone would miss the canonical node-escape shape: an init container with
# `privileged:true, runAsUser:0, capabilities.add:["SYS_ADMIN","NET_ADMIN"]` beside a compliant main container
# would score podsec-1 `all`, podsec-2 `all` with `fail:[]`, podsec-4 `na "no container adds capabilities"`
# (which removes a High-weight zero from the denominator with nothing disclosing it) and podsec-5 `all`.
# sec-12 differs: its detail says `(initContainers and ephemeral containers are not in this denominator)` and
# keeps its narrower scope. `ephemeralContainers` is included because the Pod Security Standards Baseline
# lists `spec.ephemeralContainers[*].securityContext` beside the other two, and a `kubectl debug` container
# can be privileged.
# WINDOWS PODS ARE NOT ASSESSED in this group. A pod whose spec, or whose DaemonSet's template
# (daemonsets.json), declares `spec.os.name: windows`, a nodeSelector or a required node affinity that admits
# Windows and no Linux node on `[beta.]kubernetes.io/os` or `node.kubernetes.io/windows-build` (`iswinpod`; preferred does not
# count) leaves numerator and denominator; the detail names the count (`winpx`) and a question of only
# Windows pods is `na` (`winpna`).
# CONTAINER-LEVEL `runAsNonRoot` WINS OVER POD-LEVEL, in podsec-1 and sec-15. Not `.sc.runAsNonRoot==true or
# .ps.runAsNonRoot==true`, which would let a pod-level `true` rescue a container that set `false`. Kubernetes
# documents for both fields: "If set in both SecurityContext and PodSecurityContext, the value specified in
# SecurityContext takes precedence." The test is the EFFECTIVE value (container's if set, else the pod's,
# `true` required); absent at both is a fail.
# WHY `!= null` AND NOT `//`: `(.sc.runAsNonRoot // .ps.runAsNonRoot)` is a NO-OP here because jq treats
# `false` as absent, so an explicit container `false` would fall through to the pod's `true`. `.sc` and `.ps`
# are objects-or-null, and jq answers `null` for a field of `null`, so no `//{}` guard is needed.
# WHY IT MATTERS (podsec-1 only; sec-15 reads `.spec.containers` alone): an init container with `runAsUser: 0`,
# `runAsNonRoot: false` under a pod-level `runAsNonRoot: true` enters the denominator, and under the OR it is
# PRINTED IN THE PASS SET (`N/N nonroot`, with a root container among the N).
rl podsec-1 pods daemonsets '(input|winds) as $wds|[.items[]|select((.metadata.namespace//"")|test("^(kube-|amazon-)")|not)|select((.status.phase//"")|IN("Succeeded","Failed")|not)] as $wl|[$wl[]|select(iswinpod($wds))|((.metadata.namespace//"")+"/"+(.metadata.name//"?"))] as $wn|($wn|length) as $wp|[$wl[]|select(iswinpod($wds)|not)] as $lw|[$lw[]|((.metadata.namespace//"")+"/"+(.metadata.name//"?")) as $pn|.spec.securityContext as $ps|(.spec.containers[]?,.spec.initContainers[]?,.spec.ephemeralContainers[]?)|{n:($pn+" / "+(.name//"?")),sc:.securityContext,ps:$ps}] as $c|[$c[]|select(((if (.sc.runAsNonRoot != null) then .sc.runAsNonRoot else .ps.runAsNonRoot end)==true))] as $p|if ($lw|length)==0 and $wp>0 then {pass:[],fail:[],context:(["\($wp) Windows pod(s) not assessed — this skill supports Linux nodes only"]+$wn),context_only:true} else {pass:[$p[]|.n],fail:[($c-$p)[]|.n]}+(if $wp>0 then {context:(["\($wp) Windows pod(s) not assessed — this skill supports Linux nodes only"]+$wn)} else {} end) end'
m2 podsec-1 pods daemonsets '(input|winds) as $wds|[.items[]|select((.metadata.namespace//"")|test("^(kube-|amazon-)")|not)|select((.status.phase//"")|IN("Succeeded","Failed")|not)] as $wl|([$wl[]|select(iswinpod($wds))]|length) as $wp|[$wl[]|select(iswinpod($wds)|not)] as $lw|[$lw[]|.spec.securityContext as $ps|(.spec.containers[]?,.spec.initContainers[]?,.spec.ephemeralContainers[]?)|{sc:.securityContext,ps:$ps}] as $c|($c|length) as $t|([$c[]|select(((if (.sc.runAsNonRoot != null) then .sc.runAsNonRoot else .ps.runAsNonRoot end)==true))]|length) as $ok| if ($lw|length)==0 and $wp>0 then winpna($wp) elif $t==0 then b($ok;$t)+"~\($ok)/\($t) nonroot (workloads)"+winpx($wp) elif $ok<$t then "none~\($ok)/\($t) nonroot (workloads) — \($t-$ok) container(s) not set to run as non-root, and any container not set to run as non-root fails this question"+winpx($wp) else "all~\($ok)/\($t) nonroot (workloads) — every container is set to run as non-root; any container that is not would fail this question"+winpx($wp) end'
rl podsec-2 pods daemonsets '(input|winds) as $wds|[.items[]|select((.metadata.namespace//"")|test("^(kube-|amazon-)")|not)|select((.status.phase//"")|IN("Succeeded","Failed")|not)] as $wl|[$wl[]|select(iswinpod($wds))|((.metadata.namespace//"")+"/"+(.metadata.name//"?"))] as $wn|($wn|length) as $wp|[$wl[]|select(iswinpod($wds)|not)] as $lw|[$lw[]|((.metadata.namespace//"")+"/"+(.metadata.name//"?")) as $pn|(.spec.containers[]?,.spec.initContainers[]?,.spec.ephemeralContainers[]?)|{n:($pn+" / "+(.name//"?")),c:.}] as $c|[$c[]|select((.c.securityContext.privileged//false)!=true)] as $p|if ($lw|length)==0 and $wp>0 then {pass:[],fail:[],context:(["\($wp) Windows pod(s) not assessed — this skill supports Linux nodes only"]+$wn),context_only:true} else {pass:[$p[]|.n],fail:[($c-$p)[]|.n]}+(if $wp>0 then {context:(["\($wp) Windows pod(s) not assessed — this skill supports Linux nodes only"]+$wn)} else {} end) end'
m2 podsec-2 pods daemonsets '(input|winds) as $wds|[.items[]|select((.metadata.namespace//"")|test("^(kube-|amazon-)")|not)|select((.status.phase//"")|IN("Succeeded","Failed")|not)] as $wl|([$wl[]|select(iswinpod($wds))]|length) as $wp|[$wl[]|select(iswinpod($wds)|not)] as $lw|[$lw[]|(.spec.containers[]?,.spec.initContainers[]?,.spec.ephemeralContainers[]?)] as $c|($c|length) as $t|([$c[]|select((.securityContext.privileged//false)!=true)]|length) as $ok| if ($lw|length)==0 and $wp>0 then winpna($wp) elif $t==0 then b($ok;$t)+"~\($ok)/\($t) nonpriv (workloads)"+winpx($wp) elif $ok<$t then "none~\($ok)/\($t) nonpriv (workloads) — \($t-$ok) container(s) run privileged, and any privileged container fails this question"+winpx($wp) else "all~\($ok)/\($t) nonpriv (workloads) — no container runs privileged; any privileged container would fail this question"+winpx($wp) end'
rl podsec-3 pods daemonsets '(input|winds) as $wds|[.items[]|select((.metadata.namespace//"")|test("^(kube-|amazon-)")|not)|select((.status.phase//"")|IN("Succeeded","Failed")|not)] as $wl|[$wl[]|select(iswinpod($wds))|((.metadata.namespace//"")+"/"+(.metadata.name//"?"))] as $wn|($wn|length) as $wp|[$wl[]|select(iswinpod($wds)|not)] as $lw|$lw as $p|[$p[]|select([.spec.volumes[]?|select(.hostPath)]|length==0)] as $ok|def n: (.metadata.namespace//"")+"/"+(.metadata.name//"?");if ($lw|length)==0 and $wp>0 then {pass:[],fail:[],context:(["\($wp) Windows pod(s) not assessed — this skill supports Linux nodes only"]+$wn),context_only:true} else {pass:[$ok[]|n],fail:[($p-$ok)[]|n]}+(if $wp>0 then {context:(["\($wp) Windows pod(s) not assessed — this skill supports Linux nodes only"]+$wn)} else {} end) end'
m2 podsec-3 pods daemonsets '(input|winds) as $wds|[.items[]|select((.metadata.namespace//"")|test("^(kube-|amazon-)")|not)|select((.status.phase//"")|IN("Succeeded","Failed")|not)] as $wl|([$wl[]|select(iswinpod($wds))]|length) as $wp|[$wl[]|select(iswinpod($wds)|not)] as $lw|$lw as $p|($p|length) as $t|([$p[]|select([.spec.volumes[]?|select(.hostPath)]|length==0)]|length) as $ok| if $t==0 and $wp>0 then winpna($wp) elif $t==0 then b($ok;$t)+"~\($ok)/\($t) no hostPath (workloads)"+winpx($wp) elif $ok<$t then "none~\($ok)/\($t) no hostPath (workloads) — \($t-$ok) pod(s) mount a hostPath volume, and any pod with a hostPath volume fails this question"+winpx($wp) else "all~\($ok)/\($t) no hostPath (workloads) — no pod mounts a hostPath volume; any pod with one would fail this question"+winpx($wp) end'
m2 podsec-4 pods daemonsets '(input|winds) as $wds|[.items[]|select((.metadata.namespace//"")|test("^(kube-|amazon-)")|not)|select((.status.phase//"")|IN("Succeeded","Failed")|not)] as $wl|([$wl[]|select(iswinpod($wds))]|length) as $wp|[$wl[]|select(iswinpod($wds)|not)] as $lw|[$lw[]|(.spec.containers[]?,.spec.initContainers[]?,.spec.ephemeralContainers[]?)|select(.securityContext.capabilities.add)] as $c|($c|length) as $t|([$c[]|select([.securityContext.capabilities.add[]?]|all(IN("AUDIT_WRITE","CHOWN","DAC_OVERRIDE","FOWNER","FSETID","KILL","MKNOD","NET_BIND_SERVICE","SETFCAP","SETGID","SETPCAP","SETUID","SYS_CHROOT")))]|length) as $ok| if ($lw|length)==0 and $wp>0 then winpna($wp) elif $t==0 then "na~no container adds capabilities"+winpx($wp) elif $ok<$t then "none~\($ok)/\($t) containers that add capabilities add only ones the Pod Security Standards Baseline profile allows — \($t-$ok) container(s) add a capability outside that allowlist, and any container adding one fails this question"+winpx($wp) else "all~\($ok)/\($t) containers that add capabilities add only ones the Pod Security Standards Baseline profile allows; any container adding a capability outside that allowlist would fail this question"+winpx($wp) end'
rl podsec-5 pods daemonsets '(input|winds) as $wds|[.items[]|select((.metadata.namespace//"")|test("^(kube-|amazon-)")|not)|select((.status.phase//"")|IN("Succeeded","Failed")|not)] as $wl|[$wl[]|select(iswinpod($wds))|((.metadata.namespace//"")+"/"+(.metadata.name//"?"))] as $wn|($wn|length) as $wp|[$wl[]|select(iswinpod($wds)|not)] as $lw|[$lw[]|((.metadata.namespace//"")+"/"+(.metadata.name//"?")) as $pn|(.spec.containers[]?,.spec.initContainers[]?,.spec.ephemeralContainers[]?)|{n:($pn+" / "+(.name//"?")),c:.}] as $c|[$c[]|select([.c.securityContext.capabilities.drop[]?]|any(.=="ALL"))] as $p|if ($lw|length)==0 and $wp>0 then {pass:[],fail:[],context:(["\($wp) Windows pod(s) not assessed — this skill supports Linux nodes only"]+$wn),context_only:true} else {pass:[$p[]|.n],fail:[($c-$p)[]|.n]}+(if $wp>0 then {context:(["\($wp) Windows pod(s) not assessed — this skill supports Linux nodes only"]+$wn)} else {} end) end'
m2 podsec-5 pods daemonsets '(input|winds) as $wds|[.items[]|select((.metadata.namespace//"")|test("^(kube-|amazon-)")|not)|select((.status.phase//"")|IN("Succeeded","Failed")|not)] as $wl|([$wl[]|select(iswinpod($wds))]|length) as $wp|[$wl[]|select(iswinpod($wds)|not)] as $lw|[$lw[]|(.spec.containers[]?,.spec.initContainers[]?,.spec.ephemeralContainers[]?)] as $c|($c|length) as $t|([$c[]|select([.securityContext.capabilities.drop[]?]|any(.=="ALL"))]|length) as $ok| if ($lw|length)==0 and $wp>0 then winpna($wp) elif $t==0 then "na~no workload containers" elif $ok<$t then "none~\($ok)/\($t) drop ALL (workloads) — \($t-$ok) container(s) do not drop ALL, and any container that does not drop ALL fails this question"+winpx($wp) else "all~\($ok)/\($t) drop ALL (workloads) — every container drops ALL; any container that does not would fail this question"+winpx($wp) end'
# lens-11 STATES AN ABSENCE INSTEAD OF PRINTING `0/0`: with no EC2 instances `b()` returns `na`, and the bare
# interpolation would give `na~0/0 IMDSv2`, which reads like a measurement while `na` removes the question
# from the DENOMINATOR (collect.sh condemns exactly that string). Two clusters land here: a Fargate-only
# cluster (no IMDS to reach, nothing missing) and an empty instances.json on an EC2 cluster. State is `na`
# either way; only the wording differs.
rl lens-11 instances '[.Reservations[]?.Instances[]?|select((((.State.Name)//"")|IN("terminated","shutting-down"))|not)] as $all|[$all[]|select((((.Platform//"")|ascii_downcase)=="windows"))|(.InstanceId//"?")] as $wn|($wn|length) as $w|[$all[]|select((((.Platform//"")|ascii_downcase)=="windows")|not)] as $i|[$i[]|select(.MetadataOptions.HttpTokens=="required")] as $p|def n: (.InstanceId//"?")+" ("+(.InstanceType//"?")+", HttpTokens="+(.MetadataOptions.HttpTokens//"unset")+")";if ($i|length)==0 and $w>0 then {pass:[],fail:[],context:(["\($w) Windows node(s) not assessed — this skill supports Linux nodes only"]+$wn),context_only:true} else {pass:[$p[]|n],fail:[($i-$p)[]|n]}+(if $w>0 then {context:(["\($w) Windows node(s) not assessed — this skill supports Linux nodes only"]+$wn)} else {} end) end'
# Windows instances (`.Platform == "windows"`) are left out of both lines and disclosed (`winx`); Windows only
# answers `na`. Terminated/shutting-down instances drop first (as lens-15); stopped ones restart as configured.
m lens-11 instances '[.Reservations[]?.Instances[]?|select((((.State.Name)//"")|IN("terminated","shutting-down"))|not)] as $all|([$all[]|select((((.Platform//"")|ascii_downcase)=="windows"))]|length) as $w|[$all[]|select((((.Platform//"")|ascii_downcase)=="windows")|not)] as $i|($i|length) as $t|([$i[]|select(.MetadataOptions.HttpTokens=="required")]|length) as $ok| if $t==0 and $w>0 then winna($w) elif $t==0 then "na~no EC2 instance that still exists was collected for this cluster (the instance file is empty or holds only terminated or shutting-down instances), so there was no instance metadata service to assess and NOTHING WAS MEASURED — not a pass. On a cluster with no EC2 nodes that is correct and complete: a Fargate pod reaches no IMDS, and an EKS Hybrid Node is not an EC2 instance so it has no instance metadata service either. On a cluster that lists EC2 nodes it means their instances are missing from the collection or already gone, so their IMDS settings were not measured" else b($ok;$t)+"~\($ok)/\($t) IMDSv2"+winx($w) end'
g sec-32
# sec-33 answers YES/NO (either branch satisfies it), so `kind:"existence"` says there is no total to
# cross-check. Both branches are listed, prefixed ("add-on: aws-guardduty-agent", "pod: falco/falco-xyz"),
# since they are different kinds of proof.
# THE POD BRANCH IS ANCHORED ON THE DAEMONSET NAME: a DaemonSet-owned pod `<ds>-<5 chars>` where `<ds>` is
# `aws-guardduty-agent`, `falco`, `sysdig` or `sysdig-<word>...`, or `tetragon`, alone or after a `-` (the
# Helm release prefix: the Falco chart names its DaemonSet `<release>-falco`). The 5-character end is the
# DaemonSet pod suffix, so `falco-exporter-...` and any `falco-<hash>-<id>` ReplicaSet pod do not.
# Unanchored it would credit `falcon-api-...` or `sysdigital-...`, and a namespace match would credit any
# pod in `amazon-guardduty`. A release name containing "falco" without ending in it is not recognised.
rl sec-33 addons pods 'input as $p|{pass:(([.addons[]?|select(test("guardduty"))|"add-on: "+.]|sort)+([$p.items[]?|select(([.metadata.ownerReferences[]?|select(.kind=="DaemonSet")]|length>0) and ((.metadata.name//"")|test("(^|-)(aws-guardduty-agent|falco|sysdig(-[a-z]+)*|tetragon)-[a-z0-9]{5}$")))|"pod: "+(.metadata.namespace//"")+"/"+(.metadata.name//"?")]|sort)),fail:[],kind:"existence"}'
m2 sec-33 addons pods 'input as $pods| (([.addons[]?|select(test("guardduty"))]|length)>0) as $gda| (($pods.items|map(select(([.metadata.ownerReferences[]?|select(.kind=="DaemonSet")]|length>0) and ((.metadata.name//"")|test("(^|-)(aws-guardduty-agent|falco|sysdig(-[a-z]+)*|tetragon)-[a-z0-9]{5}$"))))|length)>0) as $agent| if ($gda or $agent) then "all~a runtime-monitoring agent or add-on is present — per-node coverage and whether the agent is actually running were NOT measured" else "none~none" end'

# ── governance-compliance (6) ──
g sec-13
g sec-19
g sec-20
# EVERY enabled log type is printed, not only `audit`, with the required one marked: the remediation is an
# `--logging` update that must re-state the whole set or lose the others.
rl sec-26 cluster '([.cluster.logging.clusterLogging[]?|select(.enabled==true)|.types[]?]|unique) as $on|{pass:(if ($on|length)==0 then ["no log types enabled"] else [$on[]|.+(if .=="audit" then "  <- required by this check" else "" end)] end),fail:[],kind:"field"}'
m sec-26 cluster 'if ([.cluster.logging.clusterLogging[]?|select(.enabled==true)|.types[]?|select(.=="audit")]|length)>0 then "all~audit on" else "none~audit off" end'
g sec-36
g sec-37
```

**Governance questions** (process/organizational, not scored from cluster data — not assessed):
sec-3, sec-5, sec-7 (IAM/RBAC practice), sec-13 (env separation), sec-14 (network
separation policy), sec-19/sec-36/sec-37 (CIS/compliance scanning), sec-20 (change management), sec-22/sec-23
(EFS encryption — EFS API not collected), sec-24 (secrets-manager strategy), sec-32 (image signing),
sec-34/sec-35 (rotation cadence). All other Security questions are measured above.

---

## Implement a strong identity foundation

### sec-1: Is the EKS cluster API server endpoint configured with private access enabled?

**Detection:** 🔬 AUTO-DETECTABLE

> Private endpoint access gives the API server an in-VPC address, so cluster-internal and VPN/Direct
> Connect traffic reaches it without leaving the VPC. **On its own it does not close the public path** —
> `endpointPrivateAccess` and `endpointPublicAccess` are independent, and a cluster can have both on. A
> pass here therefore means "the private path exists", never "the API server is off the internet": that
> is `sec-2`'s question, and on this cluster the two must be read together.

**Commands:**
```bash
aws eks describe-cluster --name <CLUSTER> --region <REGION> --query "cluster.resourcesVpcConfig.endpointPrivateAccess"
```

**Remediation:** Enable private endpoint access: `aws eks update-cluster-config --name <name> --resources-vpc-config endpointPrivateAccess=true`.

---

### sec-2: Is public API server access restricted to specific CIDR ranges rather than reachable from the whole internet?

**Detection:** 🔬 AUTO-DETECTABLE

> Restricting public access CIDRs limits who can reach the API server from the internet. **This measures
> address coverage, not intent, and it decides in a fixed order that is worth knowing.**
> **Before any of that: if the public endpoint is switched off entirely (`endpointPublicAccess=false`)
> this passes and `publicAccessCidrs` is never examined** — the list is retained but inert on such a
> cluster, so a wide-open CIDR list sitting beside a disabled endpoint is not a finding here (sec-1 is
> where the endpoint itself is scored).
> **Then, any entry with a `/0` prefix fails outright**, before anything is parsed — that is `0.0.0.0/0`,
> and equally `::/0`, because the test is `endswith("/0")`. An all-internet grant in *either* address
> family is caught here, so this question is not the purely IPv4 one its middle step would suggest.
> **Second, the remaining entries are parsed individually**, merged into address ranges, and failed if
> between them they cover the whole IPv4 internet: `0.0.0.0/1` plus `128.0.0.0/1` fails exactly as
> `0.0.0.0/0` does. Because coverage only ever grows, an entry that cannot be parsed can never hide a full
> cover its siblings already prove.
> **Third and only then**, if some entry could not be parsed, the result is reported as unmeasured, naming
> just the entries that failed — so `0.0.0.0/0` sitting beside a malformed entry is a **fail**, not an
> unmeasured result.
> Two limits to read with a pass. **The coverage threshold is exactly 100%:** 255 of the 256 `/8` blocks —
> 99.609% of IPv4, every address except one `/8` — still scores a pass, reported as "restricted to 255
> CIDR range(s)". And nothing here judges whether the ranges that survive are the *right* ones: a `/24`
> you no longer control scores the same as your office egress, and the question says nothing about who
> holds credentials to authenticate once they arrive.

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
> edit per cluster, and roles are reusable across clusters. **Cross-account access is no longer a reason
> to choose IRSA:** Pod Identity reaches a role in another account through a target IAM role, and AWS
> states it "enables applications in your EKS cluster to access AWS resources across accounts through a
> process called role chaining"
> (https://docs.aws.amazon.com/eks/latest/userguide/pod-id-assign-target-role.html). The difference that
> remains is directness — AWS's own comparison table gives Pod Identity "Indirectly with role chaining"
> against IRSA's "Directly with sts:AssumeRoleWithWebIdentity"
> (https://docs.aws.amazon.com/eks/latest/best-practices/identity-and-access-management.html). IRSA
> remains fully supported and is **still required wherever Pod Identity does not run at all: Fargate
> pods, AWS Outposts, and EKS-Anywhere or self-managed Kubernetes on EC2** —
> "EKS Pod Identities aren't available on the following: AWS Outposts. Amazon EKS Anywhere. Kubernetes
> clusters that you create and run on Amazon EC2", and "Linux and Windows pods that run on AWS Fargate
> (Fargate) aren't supported"
> (https://docs.aws.amazon.com/eks/latest/userguide/pod-identities.html).
> **What this does not measure: coverage.** It counts Pod Identity associations and IRSA-annotated
> ServiceAccounts and passes as soon as one of them is real — there is no denominator. Each association
> is joined to the collected Pods that use its ServiceAccount (same namespace, `spec.serviceAccountName`,
> then the node each Pod runs on; finished `Succeeded` or `Failed` Pods and Pods not yet on a node are left out). EKS Pod Identity cannot be used by "Pods that run anywhere except Linux
> Amazon EC2 instances. Linux and Windows pods that run on AWS Fargate (Fargate) aren't supported. Pods that
> run on Windows Amazon EC2 instances aren't supported" (https://docs.aws.amazon.com/eks/latest/userguide/pod-identities.html),
> so an association whose every such Pod runs on an AWS Fargate or Windows node is NOT credited, and when
> nothing else is credited sec-6 is `none`. An association that at least one Pod on another node uses is
> credited. An association that no collected Pod uses is still credited on the association alone, and the
> detail says how many there are. Nothing decides which workloads need AWS access in the first place. A cluster where a handful of add-on
> ServiceAccounts hold associations while every application Pod still runs as `default` on node-role
> credentials passes this question; read the named associations in the list below against the Pods you
> care about before treating the pass as fleet-wide.
> **What this measures only in part: whether anything is there to serve the association.** This
> detection reads the association list, the ServiceAccounts, the cluster issuer and the account's IAM
> OIDC providers, the node list, the Pods and the DaemonSets. It credits an association only where the node list is
> non-empty and every node, Windows and AWS Fargate nodes aside, is an EKS Auto Mode node, or an `eks-pod-identity-agent` DaemonSet has at least one ready Pod; otherwise it is
> not credited, and sec-6 is then NOT ASSESSED unless working IRSA answers it — including where the only IRSA annotations are inert — so it is never passed, and never failed, on an association it could not check. There are two exceptions. On a cluster whose only nodes are AWS Fargate nodes, Pod Identity is not supported and DaemonSets do not run, so no association can be served. When every association is used only by Pods on AWS Fargate or Windows nodes (above), none of them serves a Pod either. In both cases sec-6 is `none` without working IRSA, and in the second case an agent is not needed to decide that. On EC2 nodes that are not EKS Auto Mode nodes the agent is a prerequisite: "To use EKS Pod Identity, you must deploy an agent which runs as a DaemonSet pod on every eligible worker node" (https://docs.aws.amazon.com/eks/latest/best-practices/identity-and-access-management.html), and a Pod on a node with no agent has nothing to exchange its token with, so it gets none of the association's role credentials.
> The exemption is EKS Auto Mode nodes only — "You do not need to install the EKS Pod Identity Agent on
> EKS Auto Mode Clusters. This capability is built into EKS Auto Mode"
> (https://docs.aws.amazon.com/eks/latest/userguide/pod-id-agent-setup.html) — and a cluster that mixes
> Auto Mode with managed node groups or self-managed nodes still needs the agent there: "these add-ons
> remain necessary" (https://docs.aws.amazon.com/eks/latest/userguide/eks-add-ons.html). A ready agent Pod somewhere does not show one on every such node, so confirm it with `kubectl get pods -n kube-system -o wide | grep eks-pod-identity-agent`.
> The `eks-pod-identity-token` projected volume on a Pod is necessary but NOT sufficient: EKS adds it to every Pod whose ServiceAccount has an association as the Pod is created, before Kubernetes picks its node (https://docs.aws.amazon.com/eks/latest/userguide/pod-id-how-it-works.html), so it proves the association was applied, not that an agent is there to answer it.
> **The two halves of this question are not
> symmetric:** the IRSA half DOES test its prerequisite and reports an annotation with no matching IAM
> OIDC provider as `inert`; off Auto Mode, the Pod Identity half tests only that one agent Pod is ready.
> **Windows nodes:** not assessed — this skill supports Linux nodes only.

**Commands:**
```bash
aws eks list-pod-identity-associations --cluster-name <CLUSTER> --region <REGION> --output json
kubectl get serviceaccounts -A -o json     # IRSA: annotation eks.amazonaws.com/role-arn
aws iam list-open-id-connect-providers --output json   # IRSA is inert without this
```

**Two traps this question exists to avoid:**

1. **A Pod Identity ASSOCIATION leaves no trace in the cluster.** An association is an EKS API object
   (`cluster` + `namespace` + `serviceAccount` + `roleArn`); the ServiceAccount carries **no
   annotation**. Reading only `eks.amazonaws.com/role-arn` reports a cluster with 5 working Pod
   Identity associations as having no workload identity, which is a false High-severity finding. Nor is
   the AGENT a reliable trace: it is an add-on and a DaemonSet where you install it yourself, and on an
   EKS Auto Mode cluster it is NEITHER -- associations work there with no add-on and no
   DaemonSet of that name. sec-6 therefore asks for a ready agent DaemonSet only when some node is not an
   EKS Auto Mode node, which is where AWS requires it, or when no node is listed at all, where no Auto
   Mode exemption can be shown; the rationale above states that scope.
2. **An IRSA annotation without a registered IAM OIDC provider does nothing.** The pod gets a
   projected token no IAM role will trust. With no Pod Identity association that state scores `none`, not a pass — see sec-18.

<!-- MAINTAINER NOTE — not report content. Keep each bullet in this file on ONE physical line,
     because this file's renderer (question_prose()/md_inline() in assets/render-report.py) only
     recognizes a bullet as ONE physical line — a continuation line wrapped onto the next line (no
     leading `-`/`*`) breaks out of the `<ul>` as loose sibling text, dropping the rest of the bullet
     into the report with the wrong markup. The two Remediation bullets below are one line each for
     that reason; do not rewrap them. The behaviour can be checked by
     calling question_prose()+md_inline() directly against this file. -->

**Remediation:**
- **Preferred — Pod Identity.** Install the `eks-pod-identity-agent` add-on (not needed on EKS Auto Mode nodes, which have it built in), then `aws eks create-pod-identity-association --cluster-name <name> --namespace <ns> --service-account <sa> --role-arn <arn>`. The role's trust policy names `pods.eks.amazonaws.com`; no per-cluster OIDC edit is needed.
- **IRSA.** `eksctl create iamserviceaccount --cluster <name> --name <sa> --namespace <ns> --attach-policy-arn <arn> --approve` (this requires the cluster's IAM OIDC provider and refuses to run without it; if it is missing, create it first with `eksctl utils associate-iam-oidc-provider --cluster <name> --approve` — see sec-18). Verify with `aws iam list-open-id-connect-providers`.

---

### sec-7: Do you restrict access to the kube-system namespace to super administrators only, preventing regular users from modifying critical cluster components?

**Detection:** ✋ ASK USER

> Evaluate access controls for the kube-system namespace to protect critical cluster infrastructure.

**Remediation:** Restrict kube-system access to cluster admins only. Create RBAC ClusterRoleBindings that limit kube-system namespace access to a dedicated admin group.

---

### sec-9: Do non-system ClusterRoles avoid wildcard (star) resource and verb permissions?

**Detection:** 🔬 AUTO-DETECTABLE

> Wildcard permissions grant excessive access and violate the principle of least privilege. **This
> detection finds a literal asterisk and nothing else, and its scope is wider than the word "custom"
> suggests.** A rule counts as a wildcard only when its `resources` or `verbs` list contains `*`. It
> excludes only names matching `system:*`, `eks:*` and `cluster-admin`, so Kubernetes'
> own built-in aggregated roles — `admin`, `edit` and `view` — sit inside the denominator and are
> counted as though someone on your team wrote them. They pass, because they name their resources
> explicitly: `admin` and `edit` nevertheless hold `create`, `delete`, `patch` and `update` on
> **secrets**, and `admin` holds `impersonate` plus full control of `roles` and `rolebindings`. None of
> that is a wildcard, so none of it is a finding here. A pass means at least 90% of the ClusterRoles in
> scope carry no `*` — any listed under "Counted as failing" still do — and it never means "least
> privilege": read the named grants before treating it as the latter.

**Commands:**
```bash
kubectl get clusterroles -o json
# Check rules for wildcard resources or verbs (*)
```

**Remediation:** List the ClusterRoles this check counts as failing (outside `system:*`, `eks:*` and `cluster-admin`, with a `*` in a rule's resources or verbs): `kubectl get clusterroles -o json | jq -r '.items[] | select(.metadata.name | test("^system:|^eks:|^cluster-admin$") | not) | select([.rules[]? | select(([.resources[]?] | any(. == "*")) or ([.verbs[]?] | any(. == "*")))] | length > 0) | .metadata.name'`. Replace wildcards with specific resources and verbs.

---

## Automate security best practices

### sec-17: Is cluster access granted through EKS access entries (API authentication mode) rather than the legacy aws-auth ConfigMap?

**Detection:** 🔬 AUTO-DETECTABLE

> `accessConfig.authenticationMode` decides which mechanism grants IAM identities access to the
> cluster: `API` means EKS access entries only, `API_AND_CONFIG_MAP` means access entries **and** the
> legacy `aws-auth` ConfigMap, and `CONFIG_MAP` means the ConfigMap alone. `API` passes;
> `API_AND_CONFIG_MAP` is Partial, because a principal with no access entry still gets in through the
> ConfigMap, and it is the migration step towards `API`. **This check reads that one
> cluster field and nothing else.** It does not read the `aws-auth` ConfigMap, so it reports nothing
> about which roles or users are mapped, whether those mappings are least-privilege, or whether the
> ConfigMap exists at all. On an `API`-mode cluster the ConfigMap is inert and its absence is the
> expected and desirable state — which is precisely why a pass here must not be read as "the mappings
> were reviewed". Nothing in this review reviews them.

**Commands:**
```bash
# This is the field the verdict comes from:
aws eks describe-cluster --name <CLUSTER> --region <REGION> --query "cluster.accessConfig.authenticationMode"
# Context only -- NOT read by this check. On an API-mode cluster the ConfigMap is inert, and
# "Error from server (NotFound)" is the expected result rather than a finding:
kubectl get configmap aws-auth -n kube-system -o json
```

**Remediation:** Move access off the ConfigMap and onto access entries, then switch the mode. Enable
both paths first, migrate, verify, and only then drop the ConfigMap:

```bash
aws eks update-cluster-config --name <CLUSTER> --region <REGION> \
  --access-config authenticationMode=API_AND_CONFIG_MAP
# One access entry per IAM principal that the ConfigMap used to map (a self-managed node role instead takes --type EC2_LINUX or EC2_WINDOWS and no access policy):
aws eks create-access-entry --cluster-name <CLUSTER> --region <REGION> --principal-arn <ROLE_ARN>
aws eks associate-access-policy --cluster-name <CLUSTER> --region <REGION> \
  --principal-arn <ROLE_ARN> --access-scope type=cluster \
  --policy-arn arn:aws:eks::aws:cluster-access-policy/AmazonEKSViewPolicy
```

Confirm every identity still authenticates (`aws eks list-access-entries`, then a `kubectl auth
can-i` as each principal) before going further, because **the mode transition is one-way**:
`CONFIG_MAP` can move to `API_AND_CONFIG_MAP` and then to `API`, and neither step can be reversed. Once
on `API`, delete the ConfigMap. Manage the access entries as IaC alongside the cluster, the way the
ConfigMap should have been.

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

If Pod Identity is the only mechanism in use and no ServiceAccount carries an
`eks.amazonaws.com/role-arn` annotation, this question scores `na`, not `none`: no provider is required.
`none` needs at least one such annotation with no IAM OIDC provider matching this cluster's issuer (or
no issuer at all), so the annotations are inert. Where Pod Identity serves those workloads instead, that
`none` is **not** a gap on its own — sec-6 will still pass on the associations it credits. Read the two
answers together.

**Remediation:** `eksctl utils associate-iam-oidc-provider --cluster <name> --approve`, or
`aws iam create-open-id-connect-provider --url <issuer> --client-id-list sts.amazonaws.com`. Confirm
with `aws iam list-open-id-connect-providers`, not with `describe-cluster`.

---

## RBAC Configuration

### rbac-1: Is cluster-admin restricted to the two built-in subjects expected to hold it?

**Detection:** 🔬 AUTO-DETECTABLE

<!-- MAINTAINER NOTE — not report content. Deliberately placed outside the blockquote and the
     Remediation block so the renderer does not extract it. The scorer (this file's scorer
     block, `m3 rbac-1`) also reads awsauth.json — an IAM principal mapped into
     system:masters via aws-auth is a full-cluster-admin path no ClusterRoleBinding check can see, and
     the scorer's own comment documents why. So this remediation covers both paths the question can
     fail on, and for the ClusterRoleBinding path it does not stop at "remove non-system bindings": it
     checks first that the binding being removed is not the operator's own or a break-glass account's only route to
     cluster-admin, and keeps a rollback. It warns and verifies
     before any removal, and gives the exact re-creation command for the ClusterRoleBinding case.
     Verified 2026-09-11 against docs.aws.amazon.com/eks/latest/userguide (authenticationMode: CONFIG_MAP
     vs API vs API_AND_CONFIG_MAP) and the AWS CLI reference for update-access-entry /
     disassociate-access-policy / delete-access-entry. -->

> This check exempts exactly two subjects and reports every other cluster-admin grant as a finding: the
> built-in `Group system:masters`, whose power the API server's authorizer grants directly, and
> `User eks:addon-manager`, which EKS binds through its own `eks:addon-cluster-admin` ClusterRoleBinding.
> The kind matters as much as the name — a `Group` named `eks:addon-manager` is a different subject that
> receives nothing from EKS's binding. A cluster-admin grant to anything else provides excessive
> cluster-wide access. **Three mechanisms grant cluster-admin and this question reads them to three
> different depths:** `ClusterRoleBinding` subjects are enumerated in full; the `aws-auth` ConfigMap is
> only text-matched for `system:masters`, because `jq` cannot parse the YAML it carries inside a JSON
> string, so a double-quoted escape, a YAML tag such as `!!binary`, an authenticator template such as `system:{{SessionName}}` in a `groups` entry (aws-iam-authenticator renders it from a session name the caller picks) — or the line break an editor inserts when wrapping a long `groups:`
> entry — can grant cluster-admin while defeating the match, and the same text match can fire on the
> string sitting somewhere that grants nothing; and **EKS access entries are not read at all**, which on a
> cluster whose `accessConfig.authenticationMode` is `API` leaves them the only mechanism in play (this check then skips the ConfigMap, which that mode ignores). Check
> those two by hand before treating a pass here as the whole answer. A `system:` name is no defence, and this
> check does not treat it as one: `system:anonymous`, `system:unauthenticated`, `system:authenticated`,
> `system:serviceaccounts` and `system:nodes` are all built-in names for an entire population of
> principals. Those two exemptions are the only subjects this review has observed holding cluster-admin on
> a current EKS cluster, not a guarantee about every EKS version — a legitimate third would be reported
> here for you to read and accept.

**Commands:**
```bash
kubectl get clusterrolebindings -o json
# Filter roleRef.name == "cluster-admin", check subjects
kubectl get configmap aws-auth -n kube-system -o json
# Check data.mapRoles / data.mapUsers for "system:masters" (ignored when authenticationMode is API)
```

**Remediation:** Before you remove anything: **confirm you have another way in.** A cluster-admin
binding or mapping this finding names, however stray it looks, may be the operator's own
only path to cluster-admin, or a break-glass account's. Removing it strands you on a cluster whose
entire point is that you administer it. From the identity that will remain after the change (not the
one you are about to remove), confirm it actually has cluster-admin:

```bash
kubectl auth can-i --list --as=<remaining-identity-or-serviceaccount>
# or, for an IAM principal not yet mapped to a Kubernetes username:
kubectl auth can-i '*' '*' --as=<kubernetes-username-or-group-that-will-remain>
```

Only remove the binding or mapping once that comes back with full access.

**Path 1 — a `ClusterRoleBinding` granting `cluster-admin` to a subject other than Group `system:masters` or User `eks:addon-manager`:**

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
> A ClusterRoleBinding counts against every ServiceAccount it names: a `ServiceAccount` subject, a `User`
> named `system:serviceaccount:<namespace>:<name>`, the Group `system:serviceaccounts:<namespace>` (every
> ServiceAccount in that namespace), and the Groups `system:serviceaccounts` and `system:authenticated`
> (every ServiceAccount). A binding to a default ClusterRole is not counted, whatever its subject:
> `system:basic-user`, `system:discovery` and `system:public-info-viewer` (bound by default to `system:authenticated`;
> the last also to `system:unauthenticated`); `system:service-account-issuer-discovery` and `system:cluster-trust-bundle-discovery`
> (bound by default to `system:serviceaccounts`). They grant discovery and public-data reads only; matching is by name, so an edited copy is not seen.

**Commands:**
```bash
kubectl get rolebindings -A -o json
kubectl get clusterrolebindings -o json
kubectl get serviceaccounts -A -o json
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
# Compare ServiceAccount subjects (also a User system:serviceaccount:<ns>:<name>, in either binding kind) against existing service accounts; a Group names no object to compare
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

---
