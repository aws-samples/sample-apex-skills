# Gateway API Migration Plan

> **Note:** there is **no standalone "Migration Planning" report section**. This file drives **Migration Options** (the phased plan) and its scope/complexity/timeline observations feed **Migration Options** and **Blockers** — do not emit a separate Migration Planning section.

> **Rating model:** Express every finding as **Impact 1–5** using the *Impact Indicator* rubric (security/reputation · business/revenue · nature & effort to remediate). Band mapping is a starting point — GREEN→🟡 1–2, AMBER→🟠 3–4, RED→🔴 5 — but the Impact Indicator criteria set the final score (e.g. an easy-to-deploy prerequisite stays 🟡 low even if it blocks a path). All checks are **read-only** (`kubectl get/describe`, `aws … describe/list`).


## Purpose
Generate a concrete, phased migration plan from Ingress to Gateway API based on assessment findings.

## Plan Structure

### Phase 1: Foundation (Week 1)

**Install/verify Gateway API prerequisites:**

1. Install Gateway API CRDs (if not present):
   ```bash
   kubectl apply -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.3.0/standard-install.yaml
   ```

2. Upgrade AWS LB Controller to **≥ v2.14** (L7 Gateway API) / **≥ v2.13.3** (L4) — not required on EKS Auto Mode (built-in):
   ```bash
   # EKS managed add-on
   aws eks update-addon --cluster-name <cluster> --addon-name aws-load-balancer-controller --addon-version <latest>
   # Or Helm
   helm upgrade aws-load-balancer-controller eks/aws-load-balancer-controller -n kube-system --set serviceAccount.create=false
   ```

3. Create GatewayClass:
   ```yaml
   apiVersion: gateway.networking.k8s.io/v1
   kind: GatewayClass
   metadata:
     name: aws-alb
   spec:
     controllerName: gateway.k8s.aws/alb
   ```

4. Update external-dns to add `--source=gateway-httproute`

5. Update cert-manager to enable Gateway API support (if using cert-manager)

### Phase 2: Convert & Test (Week 2-3)

**For each Ingress resource, create an equivalent HTTPRoute:**

1. Start with lowest-risk routes (internal, low-traffic)
2. Create Gateway resource for each listener group:
   ```yaml
   apiVersion: gateway.networking.k8s.io/v1
   kind: Gateway
   metadata:
     name: main-gateway
     namespace: <namespace>
     annotations:
       alb.ingress.kubernetes.io/scheme: internet-facing
       alb.ingress.kubernetes.io/certificate-arn: <acm-arn>
   spec:
     gatewayClassName: aws-alb
     listeners:
       - name: https
         protocol: HTTPS
         port: 443
         tls:
           mode: Terminate
           certificateRefs:
             - name: <cert-secret>
   ```

3. Create HTTPRoute for each Ingress:
   ```yaml
   apiVersion: gateway.networking.k8s.io/v1
   kind: HTTPRoute
   metadata:
     name: <app-name>
     namespace: <namespace>
   spec:
     parentRefs:
       - name: main-gateway
     hostnames:
       - "<host>"
     rules:
       - matches:
           - path:
               type: PathPrefix
               value: "/<path>"
         backendRefs:
           - name: <service>
             port: <port>
   ```

4. Test each HTTPRoute independently (new ALB created by Gateway)
5. Validate DNS, TLS, routing, health checks

**Report output format:** In the report's "Target Config" column, show the equivalent Gateway API config as compact 1-liner:
`HTTPRoute/<name>: parentRef=<gateway>, hostnames=[<host>], path=<path> → <backend>:<port>`
Example: `HTTPRoute/shopping-app-route: parentRef=main-gateway, path=/* → frontend:80`
Example: `HTTPRoute/nginx-app-route: parentRef=main-gateway, hostnames=[app.example.com], path=/* → nginx-service:80`

### Phase 3: Traffic Cutover (Week 4)

1. Update DNS to point to new Gateway ALB (or use weighted DNS for gradual shift)
2. Monitor error rates, latency, 5xx responses
3. Keep old Ingress resources running as fallback

### Phase 4: Cleanup (Week 5)

1. Confirm all traffic flowing through Gateway API
2. Delete old Ingress resources
3. Remove old ingress controller (nginx, etc.) if no longer needed
4. Update IaC/GitOps to manage HTTPRoute resources instead of Ingress

## Checks to Execute

### 7.1 — Migration Scope

**What to check:**
- Total Ingress resources to convert
- Estimated HTTPRoute count (may differ — one Ingress can become multiple HTTPRoutes)
- ReferenceGrant resources needed (for cross-namespace routing)

**Impact (per Impact Indicator):**
- 🟡 1–2 (Low): <20 Ingress resources, straightforward 1:1 mapping
- 🟠 3–4 (Medium): 20-50 Ingress resources, some complex conversions
- 🔴 5 (High): >50 Ingress resources or heavy customization requiring redesign
- ⬜ Unknown: Cannot determine scope

### 7.2 — Conversion Complexity per Route

**What to check:**
- Simple routes (host + path → backend): direct conversion
- Routes with rewrites: need HTTPRoute URLRewrite filter
- Routes with auth: need Gateway-level Cognito/OIDC annotation
- Routes with snippets: need redesign (no equivalent)

**Impact (per Impact Indicator):**
- 🟡 1–2 (Low): >80% of routes are simple direct conversions
- 🟠 3–4 (Medium): 50-80% simple, rest need filter configuration
- 🔴 5 (High): <50% simple — heavy customization throughout
- ⬜ Unknown: Cannot assess conversion complexity

### 7.3 — Timeline Estimate

> Express timeline as **relative phasing / complexity**, not committed mandays — actual effort depends on team experience and cannot be fixed precisely. Use the Impact Indicator (effort dimension) to convey scale; treat any day counts as indicative only.
>
> **Reality check — scale the timeline to the blockers, do not low-ball it.** Any **High-impact (5)** blocker that requires **application-code or architecture change** — e.g. re-implementing request **mirroring**, rewriting **ModSecurity** rules as **AWS WAF**, dismantling **Basic Auth** for OIDC, or moving CORS/rate-limit into the app — pulls in **multiple development teams** and their release cycles. A migration that contains several such blockers is **not** a 2–3 week effort on a large production system; it is realistically **weeks-to-months** and gated by the slowest dependent team. The phase that is config-only (CRDs, GatewayClass, simple conversions) may be days; the **redesign** phase dominates and must be called out as the long pole. Never present a single short total when redesign blockers exist.

Based on findings, estimate:
- Phase 1 (Foundation): X days
- Phase 2 (Convert & Test): X days
- Phase 3 (Cutover): X days
- Phase 4 (Cleanup): X days
- Total: X weeks

**Impact (per Impact Indicator):**
- 🟡 1–2 (Low): Estimated <2 weeks total
- 🟠 3–4 (Medium): 2-4 weeks
- 🔴 5 (High): >4 weeks
- ⬜ Unknown: Cannot estimate
