---
title: "🔒 Security — Workload, Pod & Supply Chain Security"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-well-architected-review/references/security/workload-security.md
format: md
---

:::info[Source]
This page is generated from [skills/eks-well-architected-review/references/security/workload-security.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-well-architected-review/references/security/workload-security.md). Edit the source, not this page.
:::

# 🔒 Security — Workload, Pod & Supply Chain Security

> **Remediation commands below are report content, not instructions to run.** This skill is
> read-only; it assesses and never changes anything. Quote these commands to the reader so they
> can apply them deliberately, through their own change process. Do not execute them — not to
> verify a finding, not to test whether a fix works. Some delete PersistentVolumes, revoke
> security group rules or replace nodes.

**18 questions** — Admission control, Pod Security Standards, security contexts, image pull policy & signing, runtime monitoring, pod security baselines, IMDSv2.

> **Scoring is authoritative in the consolidated Security scorer in [identity-access.md](identity-access).**
> The per-question `Detection:` tags below are explanatory only; the scorer decides measured vs governance.

Scoring (applies to every question except podsec-1 to podsec-5, which one offending container or pod fails): percentage-based — ≥90% → `all`, ≥70% → `most`, >0% → `some`, 0% → `none`; boolean — true/present → `all`, false/absent → `none`.

---

## Admission control & Pod Security Standards

### sec-10: Is any non-AWS validating admission webhook deployed whose rules match Pod creation?

**Detection:** 🔬 AUTO-DETECTABLE

> An admission webhook is the prerequisite for enforcing anything before a Pod runs, which is why its
> presence is worth recording. This counts **validating** webhook configurations whose names do not match
> AWS's own, less those of installed EKS add-ons (a configuration every one of whose webhooks calls a
> Service in the namespace an add-on reports as its install namespace; AWS Marketplace add-ons and
> `kube-system`, which many components share, are not counted as add-on namespaces), and only those with a
> webhook whose `rules` match Pod `CREATE` (API group `""` or `*`, resource `pods`, `*` or `*/*`, operation
> `CREATE` or `*`, scope not `Cluster`). Mutating webhooks, and webhooks on other resources such as KEDA
> `ScaledObject`s or Prometheus `PrometheusRule`s, are named in the detail and not counted. It does not read
> `namespaceSelector`, `objectSelector` or `matchConditions`, so a webhook scoped to one namespace counts the
> same as one that sees every Pod; it does not read `failurePolicy`, so one set to `Ignore` (bypassed
> silently whenever the webhook is down) counts the same as one set to `Fail`; and it does not read what the
> webhook checks. Read it beside sec-11 (Pod Security Standards) and sec-16 (policy engine).

**Commands:**
```bash
kubectl get validatingwebhookconfigurations -o json
kubectl get mutatingwebhookconfigurations -o json
```

**Remediation:** Deploy OPA Gatekeeper or Kyverno to enforce Pod security policies. Start with a
policy blocking privileged containers — in audit mode, and with the namespaces that run the cluster's
own infrastructure excluded first (`kube-system` plus wherever the CNI, CSI drivers, node agents and
monitoring DaemonSets live), because those legitimately need privileged access and a cluster-wide deny
blocks the add-ons the cluster needs to bring up nodes.

---

### sec-11: Are Pod Security Standards labels applied to namespaces to enforce security baselines?

**Detection:** 🔬 AUTO-DETECTABLE

> Pod Security Standards (baseline/restricted) prevent privileged containers and host access.

**Commands:**
```bash
kubectl get namespaces -o json
# Check labels starting with pod-security.kubernetes.io/
```

**Remediation:** `enforce=` is not advisory. The built-in Pod Security admission controller starts
rejecting pods that violate the level as soon as the label lands, and running pods are never evicted —
so the failure surfaces later, at the next rollout, reschedule or node replacement, which is the worst
moment to find out. Check what the level would reject, warn on it, then enforce, in that order:

```bash
# 1. What breaks? --dry-run=server returns one warning per EXISTING pod that violates the level.
kubectl label --dry-run=server --overwrite namespace <ns> \
  pod-security.kubernetes.io/enforce=baseline

# 2. Run it as a warning and an audit-log entry for real while the offenders get fixed.
kubectl label --overwrite namespace <ns> \
  pod-security.kubernetes.io/warn=baseline pod-security.kubernetes.io/audit=baseline

# 3. Only then enforce.
kubectl label --overwrite namespace <ns> pod-security.kubernetes.io/enforce=baseline
```

Node agents, CSI drivers and monitoring DaemonSets are the usual casualties: anything that needs
`hostPath`, `hostNetwork`, `hostPID` or `privileged` fails `baseline`, and `restricted` additionally
demands non-root, `seccompProfile` set and all capabilities dropped. Label each namespace at the level
its workloads can actually meet — `restricted` for your own applications, `baseline` or `privileged`
for the infrastructure namespaces — rather than enforcing one level everywhere and discovering it
during a node replacement.

---

### sec-16: Is a policy engine (Kyverno or Gatekeeper) deployed with at least one policy loaded?

**Detection:** 🔬 AUTO-DETECTABLE

> Assess the implementation of Pod-level security policies and admission control. The
> Well-Architected question behind this id also named Pod Security Standards and Pod Security Policies;
> **this detection reads neither** — sec-11 scores namespace PSS labels, PSP was removed in Kubernetes
> 1.25 and is not collected at all, so the title names only what actually runs here and the two
> questions have to be read together. **What this question scores is DEPLOYMENT: that a policy engine is
> present and carrying at least one policy object** — a Kyverno `ClusterPolicy`, or a Gatekeeper
> `Constraint`. It does not score enforcement, **and it does not report on it either**. A Pass here
> asserts that there is an engine holding rules and NOT that anything is refused at admission, and the
> detail line says exactly that in its own words, opening with `SCORED ON DEPLOYMENT ONLY`. **Whether any
> loaded policy would actually refuse a request is not judged here at all** — not in the state, and not
> as a count beside it. The three collected files do not carry enough to settle an admission outcome:
> a Kyverno ClusterPolicy marked `Enforce` that holds no `validate` rule at all refuses nothing.
> A Gatekeeper `Constraint` in `dryrun` or `warn`, and a Kyverno policy in `Audit`, all count here as a
> policy LOADED, which is the whole of what this question scores. Read the state for "there is somewhere
> to put a rule" and read nothing here about what is armed; adm-2 is the one row that says anything
> about what a policy body requires, and it says it about the body rather than about admission.
> Three limits remain. The detection does not inspect which Pod fields a policy covers, so a policy about
> labels counts exactly as one about privileged containers (adm-2 is the question that asks). **Only the
> cluster-scoped Kyverno `ClusterPolicy` kind is collected, not the namespaced `Policy` kind** — so a
> Kyverno install that keeps its rules in namespaced `Policy` objects contributes nothing here, and a
> cluster running only those reads as having no Kyverno policies at all. All four of these rows say so in
> their detail line rather than leaving you to work it out; collecting the namespaced kind is planned for
> a future version. And **an
> engine installed while carrying zero policies is only detectable for Gatekeeper**: a
> `ConstraintTemplate` with no `Constraint` object is a schema holding nothing, and that IS visible here.
> A Kyverno install with zero `ClusterPolicies` is not visible at all — from the three files this reads
> (`kyverno.json`, `constraints.json`, `constrainttemplates.json`) it is an empty `items` list, which is
> byte-for-byte what a cluster with no Kyverno produces, so it is indistinguishable from Kyverno never
> having been installed. It therefore lands on the SAME verdict as an absent engine, and for this
> question that verdict is **`none` — a counted Fail, not an exemption**. A cluster that installed
> Kyverno and loaded nothing into it reads here exactly as a cluster with no policy engine, and is marked
> down for it. Do not read this as a gap being waived. One cross-panel note, so the report does not look
> inconsistent: on that same input **all four of sec-16, adm-1, adm-2 and adm-3 answer `none`**, and each
> reads `no policy engine detected` followed by what was actually seen in the three files. An `na`
> here would make the scale non-monotonic: `na` leaves a pillar's
> scored denominator and `none` stays in it as a Fail, so a templates-only cluster — four counted Fails —
> would score BELOW a cluster with no engine at all, where an `na` would shrink the denominator. Do not convert
> any of these four to `na` to tidy something up: dropping counted Fails out of the denominator only
> raises the Security score.

**Remediation:** Deploy admission controllers (Kyverno/Gatekeeper) to enforce Pod Security Standards
and prevent privileged containers at deploy time. Exclude the namespaces that run the cluster's own
infrastructure — `kube-system` plus wherever the CNI, CSI drivers, node agents and monitoring
DaemonSets live — before anything enforces, or the policy will reject the add-ons the cluster needs to
bring up nodes.

---

### adm-1: Are admission controller policies (Gatekeeper/Kyverno) deployed on the cluster?

**Detection:** 🔬 AUTO-DETECTABLE

> Admission policies are where security and compliance rules get expressed at deploy time. **What this
> question scores is that they are DEPLOYED: at least one policy object loaded into an engine.** It does
> not score enforcement or depth: ONE loaded policy scores the same as fifty. Coverage depth is **disclosed in the
> detail line rather than scored**, via the 5-10 coverage target in the remediation below. Enforcement is
> neither scored nor reported, because the three collected files cannot settle an admission outcome
> (sec-16's panel says why). The detail line opens with `SCORED ON DEPLOYMENT ONLY` so a reader
> is told what the state does and does not claim. One limit: **an engine installed while
> carrying zero policies is only detectable for Gatekeeper**, where a `ConstraintTemplate` with no
> `Constraint` object is a schema holding nothing, and it scores `none`. A Kyverno install with zero
> `ClusterPolicies` reaches
> the three files this reads (`kyverno.json`, `constraints.json`, `constrainttemplates.json`) as an empty
> `items` list, identical to what a cluster without Kyverno produces, so it cannot be told from Kyverno
> never having been installed — and it lands on the same verdict as an absent engine, which here is
> **`none`, a counted Fail, not an exemption**. sec-16, adm-2 and adm-3 all answer `none` on that input
> too (see sec-16's panel for why moving any of the four to `na` would inflate the Security score).
> A Gatekeeper `Constraint` in `dryrun` or `warn`, or scoped only to `audit.gatekeeper.sh`, and a Kyverno
> policy whose rules resolve to `Audit`, all count here as a policy LOADED and nothing distinguishes them
> in this row's output. That is not an oversight: **this row makes no claim about what any loaded policy
> does at admission**, so there is no enforce-vs-audit split for it to get right or wrong. adm-2 is the
> only one of the four that reads a policy body, and what it reports is what the body REQUIRES, not
> what the API server would do with it. The four STATES agree on every input these three files
> can distinguish: where nothing is loaded at all (no policies and no ConstraintTemplates) all four answer
> `none`, and on a templates-only cluster all four answer `none` as well.
> A difference in either place IS drift (sec-16's panel has the reasoning).

**Commands:**
```bash
kubectl get constrainttemplates -o json 2>/dev/null
kubectl get clusterpolicies.kyverno.io -o json 2>/dev/null
```

**Remediation:** Deploy Gatekeeper or Kyverno with at least 5-10 policies covering common security
baselines (privileged containers, host networking, resource limits). Add each one in audit mode with
the cluster's own infrastructure namespaces excluded — `kube-system` plus wherever the CNI, CSI
drivers, node agents and monitoring DaemonSets live — since those legitimately use privileged and host
access, and enforcing on them blocks the add-ons the cluster needs to bring up nodes.

---

### adm-2: Is an admission policy engine deployed with at least one policy loaded, which is where a privileged-container restriction would live (whether any loaded policy restricts privileged is reported, not scored)?

**Detection:** 🔬 AUTO-DETECTABLE

> Blocking privileged containers prevents container escape attacks. **What this question scores is that
> an engine is DEPLOYED and carrying at least one policy** — the place a privileged-container restriction
> would live. Whether any loaded policy actually restricts privileged is **disclosed in the detail line
> and is not scored**: the detail opens with
> `SCORED ON DEPLOYMENT ONLY` and then names what the scan found. Whether the cluster would REFUSE a
> privileged pod is neither scored nor disclosed — sec-16's panel says why none of the
> four policy-engine rows makes that claim. So a Pass here does NOT say privileged
> pods are blocked; podsec-2 is the question that reads the pods themselves, and it is the one to check
> before treating this row as protection. The scan whose result gets disclosed is described next, and its
> two halves have different evidentiary strength. **The Kyverno half is evidenced;
> the Gatekeeper half is inferred.** For Kyverno this reads the policy body for a
> `securityContext.privileged: false` pattern **in `validate.pattern` or `validate.anyPattern` on a rule
> that itself resolves to `Enforce`** — the action and the pattern must come from the SAME rule,
> because a policy whose enforcing rule checks something else and whose privileged rule is in `Audit`
> refuses no privileged pod. Within that rule `validate.pattern` takes precedence: when it is set and
> non-null it is read **alone**, because upstream Kyverno returns from its `validate.pattern` branch
> unconditionally and never evaluates a sibling `validate.anyPattern`, so a harmless `pattern` standing
> beside a privileged-restricting `anyPattern` earns no credit here either. `validate.anyPattern` is read
> only when `pattern` is absent or `null`, and then only if **every** alternative restricts privileged
> — it is a disjunction, so one permissive alternative admits the Pod. Either way the requirement
> has to land on the **main `containers` list**: a pattern constraining only `initContainers` or
> `ephemeralContainers` still admits a privileged main container and does not count. `validate.deny` and
> `validate.cel`, which is where many policies written today express this, are **not inspected at all**, so
> a policy using one of those is NOT disclosed as demonstrably restricting privileged. That
> errs toward the weaker claim; the expression at the bottom of this panel names every `validate` form this
> half does and does not read. **For Gatekeeper there is no disclosure at all.** Which Pod field a
> `Constraint` covers is not read, so a Constraint enforcing required labels is indistinguishable here from
> one blocking privileged containers, and the detail says so in those terms: the Constraints on the cluster
> are **neither credited nor discounted** in this count, whatever their `enforcementAction`. Read the
> Constraint kinds in the list, and podsec-2's answer, before treating this row as a privileged-pod
> backstop. One thing this count is NOT: a statement that a request would be refused. `resolves to
> Enforce` here describes the action the policy document declares for that rule, read the way Kyverno
> resolves it; whether the API server acts on it is not judged by this skill (see sec-16's panel).

**Commands:**
```bash
kubectl get constraints -A -o json 2>/dev/null
kubectl get clusterpolicies.kyverno.io -o json 2>/dev/null
# Look for privileged container blocking
```

**Remediation:** Add a policy to block privileged containers: Gatekeeper `K8sPSPPrivilegedContainer`
constraint or Kyverno `disallow-privileged-containers` policy. Exempt the namespaces that run the
cluster's own infrastructure first — `kube-system` plus wherever the CNI, CSI drivers, node agents and
monitoring DaemonSets live — and list which pods run privileged today before you switch the policy to
enforce, or it will block the CNI and CSI DaemonSets the cluster needs to bring up nodes.

---

### adm-3: Is an admission policy engine deployed with at least one policy loaded?

**Detection:** 🔬 AUTO-DETECTABLE

> Audit-only policies detect but do not prevent violations, and **this row does not tell you which you
> have.** It scores deployment only — an engine is present and carrying policies — and it publishes
> nothing about what those policies do at admission: the three collected files do not carry enough to
> settle whether a request would be refused (sec-16's panel says why). One thing keeps the green
> state from being a false PASS: the heading claims only deployment, so the state is not evidence for a claim it never made — and the detail line says the same
> thing in its own words, opening with `SCORED ON DEPLOYMENT ONLY`. A heading that asked whether
> policies enforce would turn this green state into a false PASS. Enforcement depth is
> deliberately not judged by this skill. To find out what your
> policies actually do, read them: the commands below dump the fields that decide it.

**Commands:**
```bash
kubectl get constraints -A -o json 2>/dev/null
kubectl get clusterpolicies.kyverno.io -o json 2>/dev/null
# Check enforcementAction / scopedEnforcementActions, and validationFailureAction /
# validationFailureActionOverrides / rules[].validate.failureAction(Overrides)
```

**Remediation:** Enforce mode starts rejecting admission requests the moment you switch it, and it
applies to existing workloads too: a Deployment that has run untouched for a year fails its next
rollout if it violates the policy. Read the audit results first and fix or exempt everything they name:

```bash
kubectl get constraints -A -o json | jq '.items[]|{name:.metadata.name,violations:.status.totalViolations}'
kubectl get policyreports,clusterpolicyreports -A          # Kyverno's equivalent
```

Then switch one policy at a time, starting with the ones already reporting zero violations:

- Gatekeeper: `enforcementAction: deny` on the constraint (`warn` is the useful intermediate step for a constraint you have just written).
- Kyverno: `validationFailureAction: Enforce` — renamed to `failureAction` on the rule in Kyverno 1.13
  and later (`spec.validationFailureAction` migrated to `spec.rules.validate.failureAction`, per the
  v1.13.0 release notes: https://github.com/kyverno/kyverno/releases/tag/v1.13.0), where the old field
  still works but is deprecated.

Exclude the namespaces that run the cluster's own infrastructure — `kube-system` plus wherever the CNI,
CSI drivers, node agents and monitoring DaemonSets live — before enforcing anything that blocks
privileged or host access, or the policy will block the add-ons the cluster needs to bring up nodes.

---

## Container & pod hardening

### sec-12: Are workload container images pinned to a digest or an explicit tag rather than :latest?

**Detection:** 🔬 AUTO-DETECTABLE — reads `spec.containers[].image` on workload Pods.

> A mutable tag defeats image provenance. `:latest`, or a bare tag carrying no digest, can resolve to
> different bytes tomorrow than it did when you reviewed it, so what the node runs is decided by whoever
> last pushed the tag. **What this question measures is `spec.containers[].image`**: it fails a container
> whose image ends in `:latest`, and one that carries neither a tag nor an `@sha256:` digest.
> It deliberately does **not** measure `imagePullPolicy`, despite that field being the obvious place to
> look, because the value cannot be measured from a running cluster at all: the API server defaults it on
> admission — `Always` for `:latest` or an absent tag, `IfNotPresent` otherwise — so every container comes
> back from `kubectl get pods -o json` carrying a policy whether its author wrote one or not. Every
> `spec.containers` and `spec.initContainers` entry the API server returns carries one, which you can
> confirm on your own cluster (`missing` comes back `0`):
> `kubectl get pods -A -o json | jq '[.items[]|(.spec.containers[]?,.spec.initContainers[]?)]|{n:length,
> missing:[.[]|select(has("imagePullPolicy")|not)]|length}'` — so a check for an
> "explicit" pull policy would pass every cluster unconditionally and measure nothing. The pull policy
> still matters at runtime: against a digest it is irrelevant, and against a mutable tag `Always` is what
> forces a node to re-resolve the reference. It is simply not what produces this verdict. The denominator
> here is `spec.containers` on Pods outside the `kube-*` and `amazon-*` namespaces; **initContainers and
> ephemeral containers are excluded**, so a `:latest` initContainer is not a finding of this question.
> **Windows nodes:** not assessed — this skill supports Linux nodes only.

**Commands:**
```bash
kubectl get pods -A -o json
# Fails an image whose reference ends in ":latest", and one carrying NEITHER a tag nor an
# "@sha256:" digest. A plain tag such as ":stable" passes; a trailing colon with nothing after
# it ("repo/name:") is not a tag and fails.
```

**Remediation:** Pin by digest — `image: repo/name@sha256:<digest>` — or failing that to an immutable
versioned tag, and never `:latest`. Make the registry enforce it so a pushed tag cannot be moved under
you:

```bash
aws ecr put-image-tag-mutability --repository-name <REPO> --region <REGION> \
  --image-tag-mutability IMMUTABLE
```

`imagePullPolicy` is the companion control rather than the measured one: with a digest it is irrelevant,
and with a mutable tag `Always` is what forces a node to re-resolve it. Pin first — that is what makes
the result reproducible — then set the policy to match.

---

### sec-15: Do containers have security contexts configured (runAsNonRoot, readOnlyRootFilesystem, or allowPrivilegeEscalation=false)?

**Detection:** 🔬 AUTO-DETECTABLE

> Security contexts reduce the blast radius of a compromised container.
> **Windows nodes:** not assessed — this skill supports Linux nodes only.

**Commands:**
```bash
kubectl get pods -A -o json
# Check spec.containers[].securityContext
```

**Remediation:** Add `securityContext` to all containers: set `runAsNonRoot: true`,
`readOnlyRootFilesystem: true`, and `allowPrivilegeEscalation: false`. These fail closed on an existing
workload: with `runAsNonRoot: true` the kubelet refuses to start a container whose image runs as root,
and `readOnlyRootFilesystem: true` breaks anything that writes outside a mounted volume — and neither
surfaces until the next rollout or reschedule. Change one Deployment at a time, and leave the CNI, CSI
and node-agent DaemonSets in `kube-system` until last.

---

### podsec-1: Do containers run as non-root users?

**Detection:** 🔬 AUTO-DETECTABLE

> Root containers can escape to the host and compromise the node.
> **Any container not set to run as non-root fails this question.** A container passes only when its
> effective `runAsNonRoot` is `true` (its own securityContext if it sets the field, the pod's otherwise).
> The population is every regular, init and ephemeral
> container of the workload pods (namespaces outside `kube-*` and `amazon-*`, phase neither `Succeeded`
> nor `Failed`), and there is no percentage band: one such container among any
> number of compliant ones answers `none`, and only zero answers `all`. The detail keeps the compliant
> count as `n/m`.
> **Windows nodes:** not assessed — this skill supports Linux nodes only.

**Commands:**
```bash
kubectl get pods -A -o json
# Check securityContext.runAsNonRoot == true
```

**Remediation:** Set `securityContext.runAsNonRoot: true` and `runAsUser: 1000` on all containers. Use
Pod Security Standards `restricted` profile on namespaces — but `enforce=restricted` is not advisory:
the built-in admission controller starts rejecting every pod that violates it as soon as the label
lands, and running pods are never evicted, so the breakage surfaces at the next rollout or node
replacement. Dry-run it and warn on it first, and label only the namespaces whose workloads can
actually meet that level, never the infrastructure ones.

---

### podsec-2: Are containers running without privileged mode?

**Detection:** 🔬 AUTO-DETECTABLE

> Privileged containers have full host access and bypass all security boundaries.
> **Any privileged container fails this question.** The population is every regular, init and ephemeral
> container of the workload pods (namespaces outside `kube-*` and `amazon-*`, phase neither `Succeeded`
> nor `Failed`), and there is no percentage band: one privileged container among any number of
> unprivileged ones answers `none`, and only zero privileged containers answers `all`. The detail keeps
> the unprivileged count as `n/m`.
> **Windows nodes:** not assessed — this skill supports Linux nodes only.

**Commands:**
```bash
kubectl get pods -A -o json
# Check securityContext.privileged != true
```

**Remediation:** `privileged: true` grants root-equivalent access to the host — device nodes, kernel
modules, the ability to remount the host filesystem — so removing it fleet-wide in one edit is exactly
how you take down whatever depends on it. CNI plugins, CSI node-driver DaemonSets and security-agent
DaemonSets (Falco, GuardDuty's EKS agent, most service meshes' init containers) commonly need it to
function. Find out who actually needs it before touching anything:

```bash
kubectl get pods -A -o json | jq -r \
  '.items[] | select(any(.spec.containers[]?,.spec.initContainers[]?,.spec.ephemeralContainers[]?; .securityContext.privileged==true))
  | "\(.metadata.namespace)/\(.metadata.name)"'
```

Exclude `kube-system` and wherever the CNI, CSI drivers and node agents live — those are the usual
load-bearing cases. For everything else, `privileged: true` nearly always stands in for one or two
specific capabilities: add exactly what the container calls via `securityContext.capabilities.add`,
confirm the workload still runs, then remove the flag — one Deployment at a time, not fleet-wide.

---

### podsec-3: Are pods free of host path volume mounts?

**Detection:** 🔬 AUTO-DETECTABLE

> Host path mounts expose the node filesystem to containers.
> **Any pod with a hostPath volume fails this question.** The population is the workload pods
> (namespaces outside `kube-*` and `amazon-*`, phase neither `Succeeded` nor `Failed`), and there is no
> percentage band: one pod with a hostPath volume among any number of others answers `none`, and only
> zero answers `all`. The detail keeps the count of pods without one as `n/m`.
> **Windows nodes:** not assessed — this skill supports Linux nodes only.

**Commands:**
```bash
kubectl get pods -A -o json
# Check volumes[].hostPath is not used
```

**Remediation:** Replace hostPath volume mounts with PersistentVolumeClaims, ConfigMaps, or Secrets.
hostPath mounts expose the node filesystem to containers. Check who mounts one before removing it: CNI
plugins, CSI node drivers, log shippers and monitoring agents need a host path by design and stop
working without it, so this is a change to application workloads — leave `kube-system` and the
CNI/CSI/node-agent namespaces alone.

---

### podsec-4: Do containers add only the Linux capabilities the Pod Security Standards Baseline profile allows (no NET_ADMIN, SYS_ADMIN, SYS_MODULE, ALL)?

**Detection:** 🔬 AUTO-DETECTABLE

> Dangerous capabilities enable container escape and network manipulation.
> **Any container adding a capability outside the Pod Security Standards Baseline allowlist fails this
> question.** The population is the regular, init and ephemeral containers of the workload pods
> (namespaces outside `kube-*` and `amazon-*`, phase neither `Succeeded` nor `Failed`) that add at least
> one capability, and there is no percentage band: one such container answers `none`, and only zero
> answers `all`. No container adding a capability answers `na`. The detail keeps the compliant count as
> `n/m`.
> **Windows nodes:** not assessed — this skill supports Linux nodes only.

**Commands:**
```bash
kubectl get pods -A -o json
# Check every capabilities.add entry is in the PSS Baseline allowlist: AUDIT_WRITE, CHOWN, DAC_OVERRIDE,
# FOWNER, FSETID, KILL, MKNOD, NET_BIND_SERVICE, SETFCAP, SETGID, SETPCAP, SETUID, SYS_CHROOT
```

**Remediation:** `NET_ADMIN`, `SYS_ADMIN` and `ALL` are also what CNI plugins (route and interface
manipulation), CSI node drivers (mount-namespace operations) and some security-agent DaemonSets
legitimately need, so removing them from an infrastructure pod instead of an application one breaks
networking or storage cluster-wide, not just the one pod. List who adds a capability outside the
Baseline allowlist (these three, and others such as `SYS_MODULE`, `SYS_PTRACE` and `BPF`) before removing
anything:

```bash
kubectl get pods -A -o json | jq -r \
  '.items[] | .metadata.namespace as $ns | .metadata.name as $n | (.spec.containers[]?, .spec.initContainers[]?, .spec.ephemeralContainers[]?) |
  select((.securityContext.capabilities.add // []) | all(IN("AUDIT_WRITE","CHOWN","DAC_OVERRIDE","FOWNER",
    "FSETID","KILL","MKNOD","NET_BIND_SERVICE","SETFCAP","SETGID","SETPCAP","SETUID","SYS_CHROOT")) | not)
  | "\($ns)/\($n): \(.securityContext.capabilities.add)"'
```

Leave `kube-system` and the CNI/CSI/node-agent namespaces for last. For application workloads, drop the
capability, redeploy, and watch for the specific failure it was covering (a route-manipulation error, a
permission-denied on a raw socket) before calling it fixed — then add back only the exact capability the
error names, never `ALL`.

---

### podsec-5: Do containers drop ALL Linux capabilities?

**Detection:** 🔬 AUTO-DETECTABLE

> Dropping ALL capabilities and adding back only needed ones is a security best practice.
> **Any container that does not drop ALL fails this question.** The population is every regular, init and ephemeral
> container of the workload pods (namespaces outside `kube-*` and `amazon-*`, phase neither `Succeeded`
> nor `Failed`), and there is no percentage band: one container not dropping ALL among any
> number of compliant ones answers `none`, and only zero answers `all`. The detail keeps the compliant
> count as `n/m`.
> **Windows nodes:** not assessed — this skill supports Linux nodes only.

**Commands:**
```bash
kubectl get pods -A -o json
# Check capabilities.drop includes "ALL"
```

**Remediation:** Add `securityContext.capabilities.drop: ["ALL"]` to all containers, then add back only
required capabilities with `capabilities.add`. Dropping `ALL` from an infrastructure pod breaks
networking or storage cluster-wide rather than one pod, so work one workload at a time, application
namespaces first, and watch for the specific failure the dropped capability was covering before calling
it done.

---

### lens-11: Do EC2 worker nodes enforce IMDSv2 (HttpTokens=required)?

**Detection:** 🔬 AUTO-DETECTABLE

> IMDSv2 prevents SSRF attacks from stealing instance credentials.
> **EKS Hybrid Nodes:** An empty `instances.json` has three causes, not two: a Fargate-only cluster, an EKS Hybrid Nodes cluster (a hybrid node is not an EC2 instance and never appears in `describe-instances`), or a collection failure. The detail names all three.
> **Windows nodes:** not assessed — this skill supports Linux nodes only.

**Commands:**
```bash
aws ec2 describe-instances --filters "Name=tag:kubernetes.io/cluster/<CLUSTER>,Values=owned,shared" --region <REGION>
# Check MetadataOptions.HttpTokens == required
```

<!-- MAINTAINER NOTE — not report content, placed here (before **Remediation:**, after the Commands
     fence) rather than inside the Remediation body, because question_prose() in
     assets/render-report.py captures everything from "**Remediation:**" to the next `\n---`/`\n### `
     verbatim, then html-escapes it for display — a comment placed inside that span reaches the
     customer as literal "&lt;!--...--&gt;" text instead of being hidden, which is why it sits here.
     The hop-limit paragraph below deliberately states no flat rule such as "1 for a managed node group
     with no launch template, 2 when a launch template with a custom AMI is used": that split is
     documented for AL2023 only, and other AMI families do not follow it. Do not read the AMI family
     off a hop limit, or the hop limit off the AMI family: `aws eks describe-nodegroup` reports the
     node group's amiType, and `aws ec2 describe-instances` reports each instance's MetadataOptions.
     A Bottlerocket node group, for example, reports amiType BOTTLEROCKET_ARM_64 or
     BOTTLEROCKET_x86_64, never an AL2023 type. What each part below rests on:
       (1) AL2023 managed node groups: the EKS User Guide states "For
     IMDSv2 with AL2023, the default hop count for managed node groups can vary: When not using a launch
     template, the default is set to 1 ... When using a custom AMI in a launch template, the default
     HttpPutResponseHopLimit is set to 2."
     (https://docs.aws.amazon.com/eks/latest/userguide/al2023.html).
       (2) A Bottlerocket managed node group with launchTemplate: null can still run at hop 2: EKS's
     own AWSServiceRoleForAmazonEKSNodegroup generates a launch template setting
     HttpPutResponseHopLimit: 2, so its instances can report Hop: 2, Tokens: required. This is a
     DIFFERENT AMI family than (1), not a counterexample to it, and it is consistent with ImdsSupport:
     v2.0 on that AMI (see below).
       (3) ImdsSupport is not a fixed AMI-family property, which is the
     reason the remediation says "check the instance" rather than branch purely on AMI family:
     `aws ec2 describe-images` (read-only) shows that the SAME Bottlerocket
     release (v1.64.0, built the same day) carries no ImdsSupport attribute (null) on its aws-k8s-1.31
     track and ImdsSupport: v2.0 on its aws-k8s-1.34 track. AL2's EKS-optimized AMI cannot be checked
     the same way: AWS stopped publishing it on 2025-11-26 (stated on the same al2023.html
     page), and its SSM parameter for 1.34 does not resolve.
       Karpenter's httpPutResponseHopLimit:1 default is unaffected by any of the above. Source:
     https://karpenter.sh/docs/concepts/nodeclasses/ (spec.metadataOptions) -- "If metadataOptions are
     omitted from this EC2NodeClass, the following default settings are applied: httpEndpoint: enabled,
     httpProtocolIPv6: disabled, httpPutResponseHopLimit: 1, httpTokens: required". That is the Karpenter
     project's own reference documentation for its own default, which is the authority for it; no AWS
     doc restates it. Deliberately NOT corroborated with the Karpenter 1.0 launch blog post:
     blog posts sit at the bottom of this skill's source hierarchy, below the service's own
     reference documentation, and a launch announcement is a point-in-time
     claim that does not track later changes to a default. If this value needs re-checking, re-read the
     nodeclasses reference page, not an announcement. -->

**Remediation:** Require IMDSv2 (`MetadataOptions.HttpTokens=required`) so node credentials cannot be
read with a bare `GET` to `169.254.169.254`, which is what makes a server-side request forgery
profitable. Two things make this less of a one-liner than it looks:

- **Anything that only speaks IMDSv1 breaks the moment tokens are required** — old AWS SDK versions, vendored third-party agents, and any `curl http://169.254.169.254/...` in a bootstrap script or container image. The `MetadataNoToken` CloudWatch metric (namespace `AWS/EC2`) counts IMDSv1 calls per instance; get it to zero before you require tokens, not after.
- **Editing a launch template does not change instances that are already running.** A new launch template version applies only to instances launched after it, so the node group has to be rolled (or the Karpenter nodes drifted) before the setting is real. Where a node cannot be replaced yet, set it on the running instance.

```bash
aws ec2 create-launch-template-version --launch-template-id <LT_ID> --source-version '$Latest' \
  --launch-template-data '{"MetadataOptions":{"HttpTokens":"required","HttpEndpoint":"enabled"}}' \
  --region <REGION>
aws ec2 modify-instance-metadata-options --instance-id <INSTANCE_ID> --http-tokens required \
  --http-endpoint enabled --region <REGION>     # already-running instance, no replacement
```

`HttpPutResponseHopLimit` is the other half of the setting and is not part of this finding: a hop limit
of **1** is what stops a pod on the pod network from reaching IMDS at all, because the extra hop
consumes it, while **2** lets pods through. The default depends on the AMI family and how the node was
created, and it is not the same for every AMI family, so **read the effective value off the instance
rather than infer it**:

```bash
aws ec2 describe-instances --instance-ids <INSTANCE_ID> --region <REGION> \
  --query 'Reservations[].Instances[].MetadataOptions.{HopLimit:HttpPutResponseHopLimit,Tokens:HttpTokens}'
```

- **AL2023 managed node groups:** the EKS User Guide documents no launch template → hop 1 (containers
  blocked from IMDS); a custom AMI in a launch template → hop 2.
- **Other AMI families can differ from that split.** A Bottlerocket managed node group with no
  user-supplied launch template can still land on hop **2**, because EKS's own auto-generated launch
  template can set it that way — which is consistent with the AMI itself
  carrying `imds-support: v2.0`. That attribute is not fixed per AMI family either: the same Bottlerocket
  release carries it on the AMI built for one Kubernetes version track and not on the AMI built for an
  older one, so an AMI can gain it between node-group upgrades without anyone changing a setting.
- **Karpenter 1.0 and later is the one case that overrides both**: its `EC2NodeClass` defaults
  `httpPutResponseHopLimit` to **1** and `httpTokens` to `required`, specifically to block pods that
  aren't on the host network from reaching IMDS, regardless of AMI family.

Check the effective value rather than assuming a container that reads instance metadata needs it raised, and
prefer IRSA or EKS Pod Identity, which removes the reason for a pod to want node credentials at all.

---

## Supply chain & runtime security

### sec-32: Do you implement container image signing and verification (Sigstore/Cosign, AWS Signer, Notary)?

**Detection:** ✋ ASK USER

> Image signing ensures only trusted images are deployed.

**Remediation:** Deploy the Sigstore policy controller for image verification:
`helm repo add sigstore https://sigstore.github.io/helm-charts && helm repo update && helm install policy-controller sigstore/policy-controller -n cosign-system --create-namespace`.
Configure policies to reject unsigned images. That policy is admission control: every image you do not
sign — AWS add-on images, vendor charts, anything from a public registry — becomes a pod that cannot be
admitted, and a running Deployment fails its next rollout. The controller validates only namespaces that
**opt in** (it looks for the `policy.sigstore.dev/include: "true"` label), so nothing has to be excluded:
label one namespace at a time, start it in warn mode, and move it to enforce once its images all verify.

---

### sec-33: Is a runtime security monitoring agent present (GuardDuty Runtime Monitoring, Falco, Sysdig or Tetragon)?

**Detection:** 🔬 AUTO-DETECTABLE

> Runtime monitoring detects suspicious container behavior. **This detection measures presence — not
> coverage, and not health.** It passes when the GuardDuty add-on appears in the cluster's add-on list,
> or when a Pod owned by a DaemonSet is named `<daemonset>-<5 characters>` where the DaemonSet name is
> `aws-guardduty-agent`, `falco`, `sysdig` (or `sysdig-<word>…`, such as `sysdig-agent` or
> `sysdig-shield-host`) or `tetragon` — alone or after a `-`, so a Helm release prefix such as
> `security-falco-…` or `cilium-tetragon-…` counts. `falco-exporter` and `falcosidekick` are not
> detectors and do not count. A release name that contains "falco" without ending in it, or an agent
> release named without its product word, is not recognised and reads as absent. It does not
> read the Pod's phase, and it does not compare the agent's node count against the cluster's. One
> consequence follows: an add-on listed where no agent Pod is running still passes. Check
> `desiredNumberScheduled` on the agent's DaemonSet against your node count before reading this as
> fleet-wide.
> **Windows nodes:** not assessed — this skill supports Linux nodes only.

**Remediation:** Enable GuardDuty Runtime Monitoring (GuardDuty console → Protection plans → Runtime Monitoring) with automated agent configuration for Amazon EKS, which deploys the `aws-guardduty-agent` add-on; you can instead manage the agent yourself: enable Runtime Monitoring, create the GuardDuty VPC endpoint that manual management requires, then install the `aws-guardduty-agent` add-on. EKS Protection alone is audit-log monitoring and deploys no agent. Alternatively, deploy Falco: `helm repo add falcosecurity https://falcosecurity.github.io/charts && helm repo update && helm install falco falcosecurity/falco --namespace falco --create-namespace`.

---

## Image supply chain

> Filed under Security, not Cost Optimization. Both questions are ECR controls that limit what can enter
> the cluster, which the EKS Best Practices Guides cover under Security / Image Security. Scored
> in the consolidated Security scorer in [identity-access.md](identity-access).

### lens-12: Do ECR repositories have scan-on-push enabled?

**Detection:** 🔬 AUTO-DETECTABLE

> Image scanning detects vulnerabilities before deployment. **This question examines only the repositories in this account and Region that an ECR image the cluster actually pulls comes from** — main containers and init containers alike. Matching is by the full repository URI (`<account>.dkr.ecr.<region>.amazonaws.com/<name>`, the image reference without its tag or digest; a FIPS-endpoint reference, `dkr.ecr-fips`, is read as the same registry) against this account's `describe-repositories` output for the cluster's Region, so an image pulled from an ECR registry in a **different** account or Region (the shared-registry, replicated-repository and AWS-add-on case), or from any non-ECR registry, is not examined — even when a repository of the same name exists here: this review holds no credential for another account, reads repositories in one Region only, and attempts no cross-account lookup. This question never reports a score: whether or not the two lists intersect it reports "not assessed, and not a pass", because the repository-level flag does not show whether an image is scanned — and when they do not intersect, nothing is examined at all, since repositories can exist in the account and still none of them be the ones the cluster pulls.

**Commands:**
```bash
aws ecr describe-repositories --region <REGION> --query "repositories[].[repositoryUri,imageScanningConfiguration.scanOnPush]"
# Intersected by full repository URI (repositoryUri) with the ECR images the cluster pulls, tag and
# digest stripped, init containers included:
kubectl get pods -A -o json \
  | jq -r '.items[]|(.spec.containers[]?,.spec.initContainers[]?)|.image|select(test("dkr.ecr"))'
# An image whose registry account or Region differs from this one appears in the second list and never
# in the first, so it is not matched and its scan settings are never read.
```

**Analysis:** No verdict is given from the repository-level flag:
- no matched repository → `na`, not assessed (nothing was examined)
- one or more matched repositories → `na`, not assessed; the detail counts how many carry `scanOnPush`
- the flag does not show whether an image is scanned: the registry-level scanning configuration decides,
  and a repository that matches no enhanced-scanning filter is not scanned whatever its flag says
- this review does not read the registry-level scanning configuration

**Remediation:** Configure scanning at the registry level, not per repository: the repository-level
`scanOnPush` flag is deprecated and does not decide whether an image is scanned. Read the current setting
with `aws ecr get-registry-scanning-configuration --region <REGION>` and check that every repository the
cluster pulls from matches one of its rules. Add a missing filter with `aws ecr put-registry-scanning-configuration`,
whose `--rules` is the registry's whole rule list, so start from the rules the first command returned.
With enhanced scanning (`--scan-type ENHANCED`), Amazon Inspector scans repository contents continuously or on
push and charges for it, and a repository that matches no filter is not scanned. Do this in every account that
owns a registry the cluster pulls from, including the ones this check cannot see
(https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-scanning-enhanced.html; the deprecation:
https://docs.aws.amazon.com/AmazonECR/latest/APIReference/API_PutImageScanningConfiguration.html).

---

---

### lens-13: Do ECR repositories use immutable image tags?

**Detection:** 🔬 AUTO-DETECTABLE

> Immutable tags prevent tag overwriting and ensure deployment reproducibility. **Scope is the same as lens-12's:** only repositories in this account and Region whose full repository URI matches an ECR image the cluster pulls (main containers and init containers) are examined, and an image from a registry in another account or Region, or from a non-ECR registry, is not matched even when a repository of the same name exists here — so this question too can end with nothing examined, reported as "not assessed, and not a pass" rather than as a score.

**Commands:**
```bash
aws ecr describe-repositories --region <REGION> --query "repositories[].[repositoryUri,imageTagMutability]"
# Check for IMMUTABLE, on the repositories whose repositoryUri matches a cluster ECR image (tag and digest stripped):
kubectl get pods -A -o json \
  | jq -r '.items[]|(.spec.containers[]?,.spec.initContainers[]?)|.image|select(test("dkr.ecr"))'
```

**Analysis:** Use percentage-based scoring where applicable:
- ≥90% compliance → `all`
- ≥70% compliance → `most`
- >0% compliance → `some`
- 0% compliance → `none`
- For boolean: present/true → `all`, absent/false → `none`

**Remediation:** Enable immutable tags for ECR repositories:
`aws ecr put-image-tag-mutability --repository-name <name> --image-tag-mutability IMMUTABLE`.
Apply it to every repository the cluster pulls from, including the ones in other accounts this check
cannot see, using credentials for the account that owns the registry. It changes what the registry accepts, not what the cluster runs: a
pipeline that republishes a moving tag such as `latest` starts failing its push, so move those pipelines
to unique tags (or digests) first.

---
