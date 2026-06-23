# Ingress Discovery

> **Rating model:** Express every finding as **Impact 1–5** using the *Impact Indicator* rubric (security/reputation · business/revenue · nature & effort to remediate). Band mapping is a starting point — GREEN→🟡 1–2, AMBER→🟠 3–4, RED→🔴 5 — but the Impact Indicator criteria set the final score (e.g. an easy-to-deploy prerequisite stays 🟡 low even if it blocks a path). All checks are **read-only** (`kubectl get/describe`, `aws … describe/list`).


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

**Impact (per Impact Indicator):**
- 🟡 1–2 (Low): Single modern controller (AWS LB Controller v2.x) installed and healthy
- 🟠 3–4 (Medium): Multiple controllers or legacy controller (nginx-ingress, ALB Ingress Controller v1)
- 🔴 5 (High): No controller found, or controller pods in CrashLoopBackOff
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

**Impact (per Impact Indicator):**
- 🟡 1–2 (Low): IngressClass defined, default set, Ingress resources reference it explicitly
- 🟠 3–4 (Medium): IngressClass exists but Ingress resources use legacy annotation instead of `ingressClassName`
- 🔴 5 (High): No IngressClass defined, or multiple defaults causing conflicts
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

**Impact (per Impact Indicator):**
- 🟡 1–2 (Low): All controllers on supported versions; snippet hardening intact.
- 🟠 3–4 (Medium): A controller is behind/approaching EOL, or `allow-snippet-annotations=true` is set on a current controller (injection surface re-opened).
- 🔴 5 (High): An **EOL/unsupported** controller with **known CVEs** is in use (e.g. ingress-nginx `< v1.9.0`) — security exposure on a live ingress path.
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
