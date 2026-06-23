# Traffic & Routing Complexity

> **Rating model:** Express every finding as **Impact 1–5** using the *Impact Indicator* rubric (security/reputation · business/revenue · nature & effort to remediate). Band mapping is a starting point — GREEN→🟡 1–2, AMBER→🟠 3–4, RED→🔴 5 — but the Impact Indicator criteria set the final score (e.g. an easy-to-deploy prerequisite stays 🟡 low even if it blocks a path). All checks are **read-only** (`kubectl get/describe`, `aws … describe/list`).


## Purpose
Assess routing complexity and map current patterns to Gateway API HTTPRoute equivalents.

## Checks to Execute

### 5.1 — Routing Pattern Mapping

**What to check:**
- Host-based routing → HTTPRoute `hostnames` field
- Path-based routing → HTTPRoute `matches[].path`
- Default backend → HTTPRoute with no matches (catch-all)
- Complexity per Ingress resource

**How to check:**
1. For each Ingress, count `spec.rules` entries
2. Count unique hosts across all Ingress resources
3. Check path types (Prefix, Exact, ImplementationSpecific)
4. Flag ImplementationSpecific — Gateway API only supports Exact and PathPrefix

**Gateway API mapping:**
- Ingress `spec.rules[].host` → HTTPRoute `spec.hostnames[]`
- Ingress `spec.rules[].http.paths[]` → HTTPRoute `spec.rules[].matches[].path`
- Ingress `Prefix` → HTTPRoute `PathPrefix`
- Ingress `Exact` → HTTPRoute `Exact`
- Ingress `ImplementationSpecific` → ❌ Must be converted to Exact or PathPrefix

**Impact (per Impact Indicator):**
- 🟡 1–2 (Low): Simple host+path routing, all Prefix/Exact — direct HTTPRoute mapping
- 🟠 3–4 (Medium): Some ImplementationSpecific paths or regex patterns needing conversion
- 🔴 5 (High): Heavy regex routing, >20 rules per Ingress, complex rewrite chains
- ⬜ Unknown: Cannot parse routing rules

> **Path-matching semantics change — converting regex/`ImplementationSpecific` → `PathPrefix` is NOT behavior-preserving.** ingress-nginx evaluates regex paths by **rule order / regex specificity**; ALB and Gateway API use **"most specific path wins."** A hard switch can silently route traffic to the **wrong backend** or yield **404s** that generic monitoring misses. Do **not** flip path types blindly: build a **routing comparison table** (every host+path → backend) for NGINX vs the target, and **shadow/replay** representative requests to confirm 100% match **before** cutover. Treat any cluster with regex/`ImplementationSpecific` paths as needing this validation step (raise its impact accordingly).

**Report output format:** In the report's "Current Config" column, show actual config as compact 1-liner:
`Ingress/<name>: <host><path> → <backend>:<port> (<pathType>, TLS:<yes/no>)`
Example: `Ingress/shopping-app: /*→frontend:80 (Prefix, TLS:no)`
Example: `Ingress/nginx-alb: app.example.com/* → nginx-service:80 (Prefix, TLS:ACM)`

### 5.2 — Advanced Traffic Features

**What to check:**
- Canary/weighted routing → HTTPRoute `backendRefs[].weight`
- Header-based routing → HTTPRoute `matches[].headers`
- URL rewriting → HTTPRoute `filters[].urlRewrite`
- Request redirect → HTTPRoute `filters[].requestRedirect`
- Request/response header modification → HTTPRoute `filters[].requestHeaderModifier`
- Authentication → No native Gateway API equivalent (use ALB Cognito/OIDC annotation)
- Rate limiting → No native equivalent (use AWS WAF)
- CORS → No native equivalent (use application-level or WAF)

**How to check:**
1. Scan annotations for advanced features
2. Map each to Gateway API equivalent or workaround
3. Flag features with no equivalent

**Impact (per Impact Indicator):**
- 🟡 1–2 (Low): Features used have direct HTTPRoute equivalents (weighted routing, header matching, rewrites)
- 🟠 3–4 (Medium): Some features need AWS service substitution (WAF for rate limiting, Cognito for auth)
- 🔴 5 (High): Critical dependency on nginx lua/snippets with no Gateway API path
- ⬜ Unknown: Cannot determine feature usage

### 5.3 — Cross-Namespace Routing

**What to check:**
- Ingress resources referencing services in other namespaces
- Gateway API model: cross-namespace routing requires explicit ReferenceGrant
- Service mesh integration (Istio, Linkerd)

**How to check:**
1. Check Ingress backends for cross-namespace references
2. List Services of type ExternalName
3. Check for Istio VirtualService / Linkerd ServiceProfile CRDs

**Impact (per Impact Indicator):**
- 🟡 1–2 (Low): All routing within same namespace — straightforward HTTPRoute conversion
- 🟠 3–4 (Medium): Some cross-namespace routing — need to create ReferenceGrant resources
- 🔴 5 (High): Heavy service mesh integration — Gateway API migration must coordinate with mesh
- ⬜ Unknown: Cannot determine cross-namespace routing

### 5.4 — ALB IngressGroup Sharing

**What to check (read-only):** `alb.ingress.kubernetes.io/group.name` and `group.order` on each Ingress.
- Multiple Ingresses (often across namespaces) sharing one `group.name` are served by a **single ALB**. This materially affects Gateway listener design and ALB consolidation during migration.
- **Record group membership in the topology JSON and Routing Topology** — do not drop it.

### 5.5 — Declarative Blind Spot & Optional Route Verification

**Blind spot (always note when snippets are present):** topology and routing are derived from **Ingress objects only**. Routes injected via `server-snippet` / `configuration-snippet` (e.g. a raw `location` block) **do not appear** as Ingress rules/backends, so the 3D diagram and Routing Topology under-count them. State this limitation explicitly in the report whenever snippet annotations exist — these are exactly the routes that block migration.

**Optional deep read (requires `--allow-sensitive-data-access`, still read-only):**
- Enumerate snippet-injected routes: `kubectl exec <nginx-pod> -n <ns> -- nginx -T` and scan for `location` blocks not represented by an Ingress.
- Verify live L7 behavior in-cluster: from a throwaway pod, `wget/curl` each controller's ClusterIP with the `Host:` header and record the status code (200/301/308/404/5xx) in Routing Topology. This raises confidence that routing actually works (vs. config-only inference). Keep it **optional** — the assessment is config-first.

**Topology data to collect:** Record all routing patterns, hosts, paths, and features for the 3D visualization.
