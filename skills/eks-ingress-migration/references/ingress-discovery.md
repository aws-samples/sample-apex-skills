# Ingress Discovery

> **Rating model:** Express every finding as **Impact 1–5** using the *Impact Indicator* rubric. Weigh three dimensions **in strict priority order: (1) business logic / revenue — what live traffic the thing serves · (2) security / reputation · (3) effort to remediate**. **Effort is NOT a severity driver** — how hard a fix is depends on who implements it (trivial for an expert, hard for a novice), so the model must not raise or lower Impact based on remediation effort. If effort is ever mentioned, label it explicitly as an operator note, not a score input.
>
> **Three independent dimensions that stack (they do not override each other):** a single controller/route can carry (a) a **migration-difficulty** deduction (config complexity), (b) a **tech-debt** deduction (present-but-broken, ignored), and (c) a **security** deduction (CVE/EOL). Each is a separate row in the Score Breakdown and they add up.
>
> **Presence vs. absence (do not conflate — this is the core rule):** an **absent** controller (or an empty estate) is a **non-event = 0** — there is nothing to migrate, like an unbuilt road; it never inflates a finding. A **present-but-broken** controller (CrashLoopBackOff / unreachable) is **tech debt** — someone deployed it and left it jammed, which can mis-align other systems, so it earns a small deduction **plus a mandatory cleanup note**. Only a **healthy controller serving live traffic** anchors the business/security dimensions.
>
> Band mapping is a starting point — 🟡 1–2 / 🟠 3–4 / 🔴 5 — but the Impact Indicator criteria set the final score (e.g. an easy-to-deploy prerequisite stays 🟡 low even if it blocks a path). All checks are **read-only** (`kubectl get/describe`, `aws … describe/list`).


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

**Impact (per Impact Indicator — mind presence vs. absence):**
- 🟢 0 (Non-event): **No controller found / absent / empty estate** — nothing to migrate (unbuilt road). Contributes **0** to the score; never rate this as a finding. If Ingress objects exist without any controller, see the orphaned-config handling in `report-generation.md` Step 1 (still 0, but emit the Migration Crew Alert note).
- 🟡 1 (Tech debt): **Controller present but broken** (pods in `CrashLoopBackOff`, `ImagePullBackOff`, or otherwise unreachable). Deduct **1** and **emit a mandatory note**: the controller was deployed and left jammed — it serves no live traffic but can mis-align/mis-configure other systems, so the cluster owner is responsible to fix or remove it. This is *not* a migration-difficulty rating; if the broken controller also has complex config, that complexity is scored **separately** under its own categories.
- 🟡 1–2 (Low): Single modern controller (AWS LB Controller v2.x) installed and healthy
- 🟠 3–4 (Medium): Multiple controllers or legacy controller (nginx-ingress, ALB Ingress Controller v1)
- ⬜ Unknown: Cannot determine controller health

### 1.2 — IngressClass Resources

**What to check:**
- IngressClass resources defined in the cluster
- Default IngressClass annotation (`ingressclass.kubernetes.io/is-default-class: "true"`)
- Whether Ingress resources reference a specific IngressClass

**How to check:**
1. List IngressClass resources (networking.k8s.io/v1)
2. Check for default class annotation
3. Cross-reference with Ingress resources' `spec.ingressClassName`

**Impact (per Impact Indicator — mind presence vs. absence):**
- 🟢 0 (Non-event): **No IngressClass defined AND no controller / no Ingress resources** (empty estate) — nothing to migrate; contributes 0.
- 🟡 1–2 (Low): IngressClass defined, default set, Ingress resources reference it explicitly
- 🟠 3–4 (Medium): IngressClass exists but Ingress resources use legacy annotation instead of `ingressClassName`; **or** no IngressClass defined *while Ingress resources exist* (they fall back to an ambiguous/implicit default)
- 🔴 5 (High): **Multiple defaults causing conflicts** (two or more IngressClasses marked default → non-deterministic admission)
- ⬜ Unknown: Cannot determine IngressClass usage

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

**Deterministic version facts (cite in the finding):**
- **ingress-nginx `< v1.9.0`** is affected by **CVE-2023-5043 / CVE-2023-5044** (configuration-snippet / permanent-redirect annotation injection → arbitrary command execution / privilege escalation). Treat any controller `< v1.9.0` as a security finding.
- Since **v1.9.0**, `allow-snippet-annotations` defaults to **`false`** and `annotations-risk-level` to **`High`**. If a cluster sets `allow-snippet-annotations: "true"`, it re-opens the injection surface — flag it.
- AWS Load Balancer Controller: **v2.7.2+** for the ALB Ingress path; **≥ v2.13.3 (L4) / ≥ v2.14 (L7)** for Gateway API.

**Impact (per Impact Indicator — severity scales with the LIVE traffic served, not with patch effort):**
> A CVE/EOL finding is only as severe as the **business-critical traffic it currently exposes**. Anchor severity to what the controller *actually serves live*, then to security; **never** raise or lower it based on how easy the upgrade is.
- 🟢 0 (Non-event): The affected controller **serves no live traffic** — it is **absent, broken (CrashLoopBackOff/unreachable), or has zero live routes**. An unexploitable CVE on machinery that carries no traffic is a non-event; do not deduct (record it as an informational note only). *(A broken controller still earns its separate §1.1 tech-debt point — that is not a CVE deduction.)*
- 🟡 1–2 (Low): EOL/CVE controller serving only **non-critical / internal / low-traffic** routes; snippet hardening intact.
- 🟠 3–4 (Medium): A controller is behind/approaching EOL, **or** `allow-snippet-annotations=true` is set on a current controller (injection surface re-opened), serving routes of **moderate** business importance.
- 🔴 5 (High): An **EOL/unsupported** controller with **known CVEs** (e.g. ingress-nginx `< v1.9.0`) is **actively serving business-critical / revenue / public-facing live traffic** — real security exposure on a live path.
- ⬜ Unknown: Cannot read controller image/version.

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
