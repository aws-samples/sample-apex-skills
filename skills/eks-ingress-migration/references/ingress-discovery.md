# Ingress Discovery

> **Rating model:** Express every finding as **Impact 0–5** using the *Impact Indicator* rubric.
>
> **Presence is decided by estate state; severity by priority order.** Classify the estate first, then rate only what exists:
> - **Absent controller / empty estate / orphaned dead config = Non-event (0)** — nothing to migrate (an unbuilt or abandoned road); it never inflates a finding. **Carve-out — control-plane exposure survives zero routes:** a reachable, running controller on a known-CVE/EOL version is a **security finding even with zero Ingress objects**. Example: ingress-nginx's validating admission webhook (**CVE-2025-1974**, CVSS 9.8, fixed v1.11.5 / v1.12.1) is exploitable from the pod network with **no Ingress configured** and the webhook is on by default. "Zero routes" bounds *data-plane* exposure, never *control-plane* exposure.
> - **Present-but-broken controller (CrashLoopBackOff / unreachable)** splits by whether it has **bound routes** — *bound routes = Ingress objects whose `spec.ingressClassName` (or the deprecated `kubernetes.io/ingress.class` annotation) matches this controller's class, i.e. routes this controller is responsible for serving*:
>   - **With bound routes → suspected active outage.** For an in-pod data plane (ingress-nginx) the pod *is* the data plane — all replicas down means those routes are down *now*. Flag it **urgently and separately, outside the migration score** (migration difficulty is the wrong lens for a live outage). Do not fold it into a silent tech-debt 1.
>   - **With zero bound routes → tech debt (1)** + a mandatory cleanup note (deployed then abandoned; the owner must fix or remove it).
> - **Healthy controller serving live traffic** anchors the business and security dimensions at full weight. A healthy **migration-target** controller (e.g. AWS LB Controller) with nothing bound to migrate is **0 effort — do not deduct**.
>
> **Verify before you downgrade (conservative default).** "Serves no live traffic" must be *evidenced* (read-only), not inferred from pod status: for ingress-nginx confirm **all** replicas are down (one crashlooping replica while others serve is still live); for the AWS Load Balancer Controller the data plane is the **ALB/NLB**, which keeps serving registered targets while the controller pod is down or even uninstalled — check load-balancer/target-group state (`aws elbv2 describe-load-balancers`, `aws elbv2 describe-target-health --target-group-arn <arn>` for `healthy` targets, and CloudWatch `RequestCount` / `ActiveConnectionCount` on the LB), **not** the pod. **If you cannot verify zero traffic, treat the estate as live.** Where read-only evidence points to a state, say so in the report.
>
> **Priority order (sets severity and breaks ties — it does not gate presence):** (1) business logic / revenue — the live traffic at stake · (2) security / reputation · (3) effort. **Effort is NOT a severity driver** — how hard a fix is depends on who implements it (trivial for an expert, hard for a novice), so never raise or lower Impact by remediation effort; if effort is mentioned, label it an operator note. Security findings anchor on **exposure / blast radius**, business findings on **live traffic**; priority order breaks ties, it does not zero out a real security exposure just because the business traffic behind it is small.
>
> **Three independent dimensions stack (they do not override each other):** a single controller/route can carry (a) a **migration-difficulty** deduction (config complexity), (b) a **tech-debt** deduction (present-but-broken **with zero bound routes** = +1; a broken controller **with** bound routes is instead a **suspected active outage** flagged *outside* the score — not a stacked deduction), and (c) a **security** deduction (CVE/EOL). Priority order ranks the dimensions *within* one finding; stacking means each of the three gets its **own** row in the Score Breakdown and they add up.
>
> Band mapping is a starting point — 🟢 0 / 🟡 1–2 / 🟠 3–4 / 🔴 5 — but the Impact Indicator criteria set the final score (e.g. an easy-to-deploy prerequisite stays 🟡 low even if it blocks a path). All checks are **read-only** (`kubectl get/describe`, `aws … describe/list`).


## Purpose
Discover all ingress controllers, IngressClass resources, and Ingress objects in the cluster.

## Checks to Execute

### 1.1 — Ingress Controllers Installed

**What to check:**
- Deployments/DaemonSets running ingress controllers
- Common controllers: nginx-ingress, AWS LB Controller, Traefik, HAProxy, Istio, Contour, Kong

**How to check:**
1. List Deployments across all namespaces → filter for ingress-related names
2. List DaemonSets across all namespaces → filter for ingress-related names
3. Check namespaces: `ingress-nginx`, `kube-system`, `aws-load-balancer-controller`
4. List pods with labels: `app.kubernetes.io/name=ingress-nginx`, `app.kubernetes.io/name=aws-load-balancer-controller`

**Impact (per Impact Indicator — mind presence vs. absence, and verify before downgrading):**
- 🟢 0 (Non-event): **No controller found / absent / empty estate** — nothing to migrate (unbuilt road). Contributes **0**; never rate this as a finding. If Ingress objects exist without any controller, see the orphaned-config handling in `report-generation.md` Step 1 (still 0, but emit the Migration Crew Alert note).
- ⚠️ **Active outage (NOT a migration-score item):** controller **present but broken** (`CrashLoopBackOff` / `ImagePullBackOff` / unreachable) **AND Ingress objects are bound to it**. For an in-pod data plane (ingress-nginx) those routes are down *now* — surface it as an **urgent flag, separately and outside the 0–100 score** (a live-outage question, not a migration-difficulty one). **Verify first:** for ingress-nginx confirm **all** replicas are down (a multi-replica controller can serve while one pod crashloops); for the AWS LB Controller check the **ALB/target-group** state (the ALB keeps serving while the pod is down). If you cannot verify zero traffic, treat it as live.
- 🟡 1 (Tech debt): **Controller present but broken with zero bound routes** — deployed then abandoned. Deduct **1** and **emit a mandatory cleanup note**: it carries no live traffic but can mis-align/mis-configure other systems, so the cluster owner must fix or remove it. This is *not* a migration-difficulty rating; if it also has complex config, that complexity is scored **separately** under its own categories.
- 🟢 0 / 🟡 1–2 (Low): Single healthy modern controller. A healthy **migration-target** controller (AWS LB Controller v2.x) with nothing bound to migrate is **0 effort — do not deduct**; a healthy controller you are migrating *from* (e.g. nginx) that serves live routes is 🟡 1–2.
- 🟠 3–4 (Medium): Multiple controllers, or a legacy controller (nginx-ingress, ALB Ingress Controller v1). A broken controller still counts as a present controller for the "multiple controllers" assessment; its brokenness is scored by the rows above, not double-counted here.
- Security carve-out: a **reachable known-CVE/EOL controller is a security finding even with zero routes** (control-plane exposure) — rate it under §1.4 (Controller Currency, EOL & CVE Exposure), not here.
- ⬜ Unknown: Cannot determine controller health — state what to check and why.

### 1.2 — IngressClass Resources

**What to check:**
- IngressClass resources defined in the cluster
- Default IngressClass annotation (`ingressclass.kubernetes.io/is-default-class: "true"`)
- Whether Ingress resources reference a specific IngressClass

**How to check:**
1. List IngressClass resources (networking.k8s.io/v1)
2. Check for default class annotation
3. Cross-reference with Ingress resources' `spec.ingressClassName`

**Impact (per Impact Indicator — mind presence vs. absence; the behaviors below are version-specific — state them correctly):**
- 🟢 0 (Non-event): **No controller installed** — IngressClass findings are moot (nothing reconciles them, whether or not Ingress objects exist); route through the `report-generation.md` §1.0 short-circuit. Also 0 for an empty estate (no IngressClass, no controller, no Ingress).
- 🟡 1–2 (Low): IngressClass defined, a default set, and Ingress resources reference it explicitly via `ingressClassName`.
- 🟠 3–4 (Medium): IngressClass exists but Ingress resources use the deprecated `kubernetes.io/ingress.class` annotation instead of `ingressClassName`; **or** Ingress resources exist with **no class and no default IngressClass set**. Spec-compliant controllers **are permitted to ignore Ingresses without a class** (IngressClass API: *"implementations may choose to ignore Ingresses without a class specified"*); ingress-nginx serves them only if started with `--watch-ingress-without-class=true` (**default `false`**) or if an IngressClass is marked default (`ingressclass.kubernetes.io/is-default-class: "true"`). The real risk is **silent non-reconciliation** — routes quietly not served — not an "ambiguous/implicit default".
- 🔴 5 (High): **Multiple IngressClasses marked default.** On **all EKS-supported Kubernetes versions (v1.25+)** the `DefaultIngressClass` admission plugin **silently assigns the newest default** (by `creationTimestamp`, alphabetically-lowest name as tiebreak) to a classless Ingress — admission **succeeds**, it does **not** reject. The real risk is therefore **silent misrouting / cutover ambiguity**: a classless Ingress quietly binds to a class nobody intended, so traffic can land on the wrong controller during a cutover. This is the source-of-truth behavior, verified in the `DefaultIngressClass` admission-plugin code across tags v1.25 → v1.36 and its merge PR [kubernetes/kubernetes#110974](https://github.com/kubernetes/kubernetes/pull/110974). *(Historical note — Kubernetes **≤ v1.24 only**: the plugin rejected creation of a classless Ingress while multiple defaults existed; that behavior was removed in **v1.25.0** by the PR above. The kubernetes.io [Default IngressClass](https://kubernetes.io/docs/concepts/services-networking/ingress/#default-ingress-class) concept page still describes the old rejection behavior — it is **stale** for the versions this skill targets and must not be read as a live EKS outcome.)* Either way the remediation is identical: keep exactly **one** default IngressClass.
- ⬜ Unknown: Cannot determine IngressClass usage.

### 1.3 — Ingress Resource Inventory

**What to check:**
- Total Ingress resources across all namespaces
- Which namespaces have Ingress resources
- Ingress resources without an IngressClass (will use default)

**How to check:**
1. List all Ingress resources (networking.k8s.io/v1) across all namespaces
2. Count per namespace
3. Check each for `spec.ingressClassName` or `kubernetes.io/ingress.class` annotation

**Impact (per Impact Indicator):**
- 🟡 1–2 (Low): All Ingress resources have explicit IngressClass, manageable count (<50)
- 🟠 3–4 (Medium): Some Ingress resources missing IngressClass, or high count (50-200)
- 🔴 5 (High): >200 Ingress resources, or many without IngressClass assignment
- ⬜ Unknown: Cannot list Ingress resources

### 1.4 — Controller Currency, EOL & CVE Exposure

**What to check (read-only):**
- The container image **tag/version** of each ingress controller.
- Whether that version is **end-of-life / unsupported** or carries known CVEs.
- For ingress-nginx specifically: whether **snippet annotations are enabled** (injection surface).

**How to check (read-only):**
1. `kubectl get deploy <controller> -n <ns> -o jsonpath='{.spec.template.spec.containers[0].image}'` — extract the version tag for every controller found in 1.1.
2. Compare each version against the project's supported/EOL matrix.
3. For ingress-nginx, read the controller ConfigMap: `kubectl get cm <controller> -n <ns> -o jsonpath='{.data.allow-snippet-annotations} {.data.annotations-risk-level}'`.
4. **Admission-webhook exposure (required for the control-plane CVE band below):** confirm whether the validating admission webhook is actually present and reachable — do NOT assume from the version alone. Run `kubectl get validatingwebhookconfigurations` and look for the ingress-nginx entry (default name `ingress-nginx-admission`); cross-check the controller Deployment args and the `ingress-nginx-controller-admission` Service. **These object names are built from the chart's *fullname*, not the bare release name: it is the release name when that already contains the chart name, otherwise `<release>-ingress-nginx`. So the VWC is `ingress-nginx-admission` for a release named `ingress-nginx`, but `<release>-ingress-nginx-admission` otherwise (and the Service likewise `…-controller-admission`) — match by the controller's owner references / labels, not just the literal default names.** The webhook ships **enabled by default** in Helm installs. Decide exposure as follows and **record the exact state** (`webhook: exposed | not-exposed | unverified`) in the finding — do not collapse it to a bare present/absent flag:
   - **Exposed** — the controller Deployment is started with a **non-empty** `--validating-webhook=<address>` arg (e.g. `--validating-webhook=:8443`, the Helm default), so the **webhook server is actually listening on the controller pod** (pod-IP:8443). This is the CVE-2025-1974 attack surface: the exploit reaches the pod's webhook server **directly over the pod network**, so on a `< v1.11.5 / < v1.12.1` controller the control-plane path is live **regardless of route count** (🔴 5 band). A present `ingress-nginx-admission` VWC and a backed `ingress-nginx-controller-admission` Service **corroborate** that the webhook is also wired into the API server, but it is the **listening server** that makes it exploitable.
   - **Not exposed** — the **necessary** condition is that the **webhook server is not listening**: the controller Deployment has **no** (or an empty) `--validating-webhook=<address>` arg. That flag takes a **service-address string, not a boolean** — there is no `--validating-webhook=false` form; when the value is absent/empty the server is simply never started. An absent VWC and/or an absent admission Service are **corroborating** signals (a Helm `controller.admissionWebhooks.enabled=false` install drops the VWC, the Service **and** the arg together) but do **NOT**, on their own, close the path: the VWC and admission Service are **API-server-side plumbing**, whereas the exploit targets the pod's listening webhook server at pod-IP:8443 directly. Only a **confirmed** server-not-listening (arg absent/empty) drops the 🔴 5 band; then note it and fall back to the data-plane assessment.
   - **Unverified (fail closed)** — if you **cannot confirm the server is not listening** — the controller Deployment args are `Forbidden`/unreadable, or only a partial read succeeded (e.g. you could read the VWC or the Service but not the args) — you have **not** verified the necessary condition, so **default to exposed** for a `< v1.11.5 / < v1.12.1` controller (the webhook is on by default; a missing read must not silently drop the 🔴 5 band). This **takes precedence** over any VWC/Service-absent observation: an absent VWC with unreadable controller args is still **Unverified → exposed**, because the absence of the API-server plumbing does not prove the pod's webhook server is down. Score it as exposed and flag *"webhook state unverified — assumed exposed; re-check the controller args with cluster-admin."*

**Deterministic version facts (cite in the finding):**
- **ingress-nginx `< v1.9.0`** is affected by **CVE-2023-5043 / CVE-2023-5044** (configuration-snippet / permanent-redirect annotation injection → arbitrary command execution / privilege escalation). Treat any controller `< v1.9.0` as a security finding.
- Since **v1.9.0**, `allow-snippet-annotations` defaults to **`false`** and `annotations-risk-level` to **`High`**. If a cluster sets `allow-snippet-annotations: "true"`, it re-opens the injection surface — flag it.
- AWS Load Balancer Controller: **v2.7.2+** for the ALB Ingress path; **≥ v2.13.3 (L4) / ≥ v2.14 (L7)** for Gateway API.

**Impact (per Impact Indicator — anchor on EXPOSURE / blast-radius for security, and on live traffic for business; never on patch effort):**
> A CVE/EOL finding's severity comes from what it **exposes**, not how hard the upgrade is. Two exposure surfaces exist and are **independent**:
> - **Data-plane exposure** scales with the **live traffic the controller serves** (business-critical routes > internal > none).
> - **Control-plane exposure** is the controller's own attack surface (e.g. ingress-nginx's validating admission webhook) and **exists whenever the controller process is running and reachable — regardless of how many routes it serves.** "Zero routes" does NOT imply "not exploitable."
- 🟢 0 (Non-event): The controller is **absent, or fully down** — all replicas `CrashLoopBackOff`/unreachable, so neither the data plane nor the admission webhook is serving. Record as an informational note, deduct 0. *(A broken-with-zero-routes controller still earns its separate §1.1 tech-debt point — that is not a CVE deduction; a broken-with-bound-routes controller is an active outage, handled in §1.1.)*
- 🟡 1–2 (Low): EOL/CVE controller serving only **non-critical / internal / low-traffic** routes, with no known control-plane RCE; snippet hardening intact.
- 🟠 3–4 (Medium): A controller is behind/approaching EOL, **or** `allow-snippet-annotations=true` is set on a current controller (injection surface re-opened), serving routes of **moderate** business importance.
- 🔴 5 (High): Either **(a)** an **EOL/unsupported controller with known CVEs** (e.g. ingress-nginx `< v1.9.0`) **actively serving business-critical / revenue / public-facing live traffic**; **or (b)** a **running controller exposing a known control-plane RCE regardless of route count** — e.g. ingress-nginx `< v1.11.5 / < v1.12.1` with the validating admission webhook **exposed** (or **unverified** — see the tri-state in "How to check" step 4; unverified defaults to exposed) (**CVE-2025-1974**, CVSS 9.8): exploitable from the pod network with **zero Ingress objects**, leading to cluster-wide Secret disclosure / takeover. A **healthy, zero-route** vulnerable controller is a **critical** finding here — not a non-event.
- ⬜ Unknown: Cannot read controller image/version — state what to check.

> Every controller version found MUST appear in the report (Current Configuration + Ingress Discovery), with EOL/CVE status called out — do not roll multiple controllers into one line.

> **Remediation sequencing (SAFETY — do not get this wrong):** setting `allow-snippet-annotations: false` is a **breaking change** for any Ingress currently using snippet annotations — the controller drops those routes and can cause **immediate downtime**. If snippet-using ingresses exist (cross-check §3.1), you MUST NOT recommend disabling it as an "urgent / Day-1 / immediate" action. Sequence it **after** those routes are migrated or redesigned. The recommendation wording must read "re-disable snippet annotations **after** migrating the snippet routes", never "urgent: set false now". The same applies to retiring an EOL controller that still serves live routes — migrate first, retire last.

### 1.5 — EKS Auto Mode Detection

**What to check (read-only):**
- Whether the cluster runs **EKS Auto Mode** (changes how load balancing is provided).

**How to check (read-only):**
1. `aws eks describe-cluster --name <cluster> --query 'cluster.computeConfig'` — Auto Mode is enabled when `computeConfig.enabled = true` (with managed `nodePools`).
2. Recognize Auto Mode's managed load-balancing IngressClass: `spec.controller: eks.amazonaws.com/alb` (parameters `apiGroup: eks.amazonaws.com`, `kind: IngressClassParams`); NLB via `loadBalancerClass: eks.amazonaws.com/nlb`. This is **distinct** from the self-managed LBC (`ingress.k8s.aws/alb`).

**Why it matters:** on Auto Mode the ALB Ingress path needs **no self-managed LBC install** (it's built in); a `eks.amazonaws.com/alb` IngressClass is a *managed* controller, not a missing one. Gateway API L7 still requires the LBC ≥ v2.14 unless/until Auto Mode exposes it natively.

**Impact (per Impact Indicator):** informational — record Auto Mode status in Current Configuration; it does not by itself carry a migration impact, but it changes the Migration Options guidance.
