# Gateway API Migration Plan

> **Note:** there is **no standalone "Migration Planning" report section**. This file drives **Migration Options** (the phased plan) and its scope/complexity/timeline observations feed **Migration Options** and **Blockers** — do not emit a separate Migration Planning section.

> **Rating model:** Express every finding as **Impact 0–5** using the *Impact Indicator* rubric, weighing three dimensions **in priority order: (1) business logic / revenue — the live traffic at stake · (2) security / reputation · (3) effort to remediate**. **Effort is NOT a severity driver** — a fix being easy or hard never moves the score (it depends on who implements it). **Presence is decided by estate state** — absent controller / empty estate / orphaned dead config = **non-event (0)**; a broken controller is **tech debt (1)** with zero bound routes or a **suspected active outage** (flagged outside the score) with bound routes; a running controller with a **control-plane CVE counts even at zero routes**. See `ingress-discovery.md` for the full presence/stacking rules. Band mapping is a starting point — 🟢 0 / 🟡 1–2 / 🟠 3–4 / 🔴 5 — but the Impact Indicator criteria set the final score (e.g. an easy-to-deploy prerequisite stays 🟡 low even if it blocks a path). All checks are **read-only** (Kubernetes API `get`/`list`, AWS `Describe`/`List`).


## Purpose
Generate a concrete, phased migration plan from Ingress to Gateway API based on assessment findings.

## Plan Structure

### Phase 1: Foundation (Week 1)

**Install/verify Gateway API prerequisites:**

1. Install the standard Gateway API CRDs (if not present) — **pick the version that pairs with the controller line you land on in step 2**, because the pairing is not interchangeable:

   | Controller line | Standard CRDs | Notes |
   |---|---|---|
   | v3.4.0 (the tag the `lbc-migrate` CLI is built from) | **v1.5.0** | L4 routes still need the experimental channel |
   | **v3.5.0** (the recommended target) | **v1.6.0** | LBC v3.5.0 is built for Gateway API v1.6.0; TCPRoute/UDPRoute are in the standard channel from v1.6.0, so no experimental install is needed for L4 |

   ```
   # v1.6.0 — pair with a v3.5.0 controller (see step 2)
   kubectl apply --server-side=true -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.6.0/standard-install.yaml
   ```

   Also install the **LBC Gateway API CRDs** (`LoadBalancerConfiguration`, `TargetGroupConfiguration`, `ListenerRuleConfiguration`) — the ALB Gateway controller does not enable without them, and Phase 2 configures the load balancer through them.

2. Upgrade AWS LB Controller to **≥ v3.0.0** (the Gateway API production floor; the **v3.5.0** line is the recommended target) — still required on EKS Auto Mode, whose built-in controller does not provide Gateway API. There is **no `aws-load-balancer-controller` EKS add-on** — it is not in the AWS add-on catalog nor the community add-on list, so install and upgrade go through Helm (or the release manifests):
   ```
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

> **Automate this phase with `lbc-migrate` when the estate is already on LBC ALB Ingress.** The official **LBC Ingress → Gateway API toolkit** (`lbc-migrate` CLI + Migration Console) translates the Ingress resources into Gateway API manifests and previews the result with a dry-run before any ALB is created. Prerequisites are the same runtime requirement as the hand-authored path below — controller **≥ v3.0.0**, the Gateway API production floor — plus the **standard Gateway API CRDs the controller line targets** (v1.5.0 for v3.4.0, v1.6.0 for the v3.5.0) and the CLI built from the **LBC v3.4.0** tag. Full flow, prerequisites, output resources and limitations: `references/lbc-migrate-toolkit.md` — don't restate them here. The hand-authored steps below remain the fallback for the toolkit's **skip-or-warn** cases, for clusters **below that production floor** (where upgrading the controller to the v3.5.0 release line is usually the better first move — it clears the floor *and* still carries the CLI), and for EKS Auto Mode. `lbc-migrate` converts **LBC Ingress**, not raw NGINX — do the NGINX → LBC Ingress hop first (`references/alb-migration.md`).

**For each Ingress resource, create an equivalent HTTPRoute:**

1. Start with lowest-risk routes (internal, low-traffic)
2. Create a Gateway resource for each listener group. **The ALB is configured through the `LoadBalancerConfiguration` CRD, not through `alb.ingress.kubernetes.io/*` annotations** — those are Ingress/Service-only and are ignored on a Gateway. Two consequences worth stating explicitly, because both fail silently:
   - `scheme` **defaults to `internal`**, so omitting it gives you a private ALB, not an internet-facing one.
   - **TLS certificates cannot be set via the listener's `certificateRefs` field.** Upstream states this outright; the cert comes from `listenerConfigurations[].defaultCertificate` (an ACM ARN) or from hostname-based certificate discovery. A Gateway that only sets `certificateRefs` gets **no certificate on the listener**.

   ```yaml
   apiVersion: gateway.k8s.aws/v1
   kind: LoadBalancerConfiguration
   metadata:
     name: main-gateway-lb
     namespace: <namespace>
   spec:
     scheme: internet-facing          # REQUIRED for public: default is internal
     listenerConfigurations:
       - protocolPort: HTTPS:443
         defaultCertificate: <acm-arn>   # ACM ARN; NOT a Kubernetes Secret
         sslPolicy: ELBSecurityPolicy-TLS13-1-2-2021-06
   ---
   apiVersion: gateway.networking.k8s.io/v1
   kind: Gateway
   metadata:
     name: main-gateway
     namespace: <namespace>
   spec:
     gatewayClassName: aws-alb
     infrastructure:
       parametersRef:                 # how the LB config attaches
         group: gateway.k8s.aws
         kind: LoadBalancerConfiguration
         name: main-gateway-lb
     listeners:
       - name: https
         protocol: HTTPS
         port: 443
         hostname: <fqdn>             # drives certificate discovery
         tls:
           mode: Terminate
           # No certificateRefs: unsupported by LBC. Cert is set above.
   ```

   Per-target-group settings (health checks, target type, attributes) move to `TargetGroupConfiguration`, and per-rule settings such as OIDC authentication move to `ListenerRuleConfiguration.authenticateOIDCConfig` — again, not annotations.

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

> **Validate the full cutover procedure in a non-production cluster before executing against production.** "Lowest-risk routes" and keeping the old Ingress as fallback are mitigations, not a substitute for a non-prod gate — a low-risk production route is still production, and path-matching semantic changes can silently route traffic to the wrong backend (see `references/traffic-routing.md`).

1. Update DNS to point to new Gateway ALB (or use weighted DNS for gradual shift)
2. Monitor error rates, latency, 5xx responses
3. Keep old Ingress resources running as fallback

### Phase 4: Cleanup (Week 5)

1. Confirm all traffic flowing through Gateway API
2. Delete old Ingress resources
3. Remove the old ingress controller (nginx, etc.) if no longer needed — **`helm uninstall` the release, never `kubectl delete deploy` alone.** The ingress-nginx chart also owns an `ingress-nginx-admission` ValidatingWebhookConfiguration (`failurePolicy: Fail`, no selectors); if the Deployment goes and the webhook stays, its Service has no endpoints and the API server rejects **every** Ingress create/update in the cluster — including re-applying the migrated resources and any GitOps reconcile. For a non-Helm install, delete the admission `ValidatingWebhookConfiguration` and its Service explicitly.
4. Update IaC/GitOps to manage HTTPRoute resources instead of Ingress

## Checks to Execute

> **These §7 checks are planning signals, NOT scored findings.** §7.1 scope, §7.2 conversion complexity, and §7.3 timeline restate what sections 1–5 already scored (scope↔Scale/Volume, complexity↔Feature-Gap/Routing) and feed the phased plan and Blockers. **Do not add any §7.x row to the Score Breakdown** (see `report-generation.md` §1.1 quarantine) — that would double-count. Timeline in particular is never an Impact score.

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

> Express timeline as **relative phasing**, not committed mandays — actual duration depends on team experience and cannot be fixed precisely. **Timeline is a planning output, not a scored Impact — do not assign it an Impact 1–5** (effort/duration never sets severity; see the Impact Indicator). Treat any day counts as indicative only.
>
> **Reality check — scale the timeline to the blockers, do not low-ball it.** Any **High-impact (5)** blocker that requires **application-code or architecture change** — e.g. re-implementing request **mirroring**, rewriting **ModSecurity** rules as **AWS WAF**, dismantling **Basic Auth** for OIDC, or moving CORS/rate-limit into the app — pulls in **multiple development teams** and their release cycles. A migration that contains several such blockers is **not** a 2–3 week effort on a large production system; it is realistically **weeks-to-months** and gated by the slowest dependent team. The phase that is config-only (CRDs, GatewayClass, simple conversions) may be days; the **redesign** phase dominates and must be called out as the long pole. Never present a single short total when redesign blockers exist.

Based on findings, estimate:
- Phase 1 (Foundation): X days
- Phase 2 (Convert & Test): X days
- Phase 3 (Cutover): X days
- Phase 4 (Cleanup): X days
- Total: X weeks

**Timeline (planning output — NOT an Impact score):** express as relative phasing derived from the blockers; never assign the timeline an Impact 1–5.
- **Config-only** (CRDs, GatewayClass, simple conversions): days.
- **Redesign-dominated** (Tier-A blockers, app/architecture changes across teams): weeks-to-months — gated by the slowest dependent team; call it out as the long pole.
- If you cannot estimate: say so, and scope the timeline to the identified blockers.
