# Ingress Resource Analysis

> **Rating model:** Express every finding as **Impact 1–5** using the *Impact Indicator* rubric (security/reputation · business/revenue · nature & effort to remediate). Band mapping is a starting point — GREEN→🟡 1–2, AMBER→🟠 3–4, RED→🔴 5 — but the Impact Indicator criteria set the final score (e.g. an easy-to-deploy prerequisite stays 🟡 low even if it blocks a path). All checks are **read-only** (`kubectl get/describe`, `aws … describe/list`).


## Purpose
Analyze existing Ingress resources to determine what must be converted to HTTPRoute and identify conversion complexity.

## Checks to Execute

### 3.1 — Annotation Inventory & Gateway API Mapping

**What to check:**
- All annotations on every Ingress resource
- Which annotations have direct HTTPRoute equivalents
- Which require Gateway-level config, policy attachments, or AWS service substitution
- Which have no Gateway API equivalent (blockers)

**How to check:**
1. List all Ingress resources across all namespaces
2. For each, extract all annotations
3. Map each annotation to its Gateway API equivalent:

**Annotation mapping to Gateway API:**

| Current Annotation | Gateway API Equivalent |
|---|---|
| `nginx.ingress.kubernetes.io/rewrite-target` | HTTPRoute `filters[].urlRewrite` |
| `nginx.ingress.kubernetes.io/ssl-redirect` | Gateway listener `tls` config |
| `nginx.ingress.kubernetes.io/cors-*` | No native equivalent — use AWS WAF or application-level |
| `nginx.ingress.kubernetes.io/auth-url` | No equivalent — use ALB + Cognito/OIDC via Gateway annotation |
| `nginx.ingress.kubernetes.io/canary-*` | HTTPRoute `backendRefs[].weight` (traffic splitting) |
| `nginx.ingress.kubernetes.io/affinity` | No native equivalent — use `alb.ingress.kubernetes.io/target-group-attributes` on Gateway |
| `nginx.ingress.kubernetes.io/configuration-snippet` | ❌ No equivalent — redesign needed |
| `nginx.ingress.kubernetes.io/server-snippet` | ❌ No equivalent — redesign needed |
| `nginx.ingress.kubernetes.io/lua-resty-waf` | ❌ No equivalent — use AWS WAF |
| `alb.ingress.kubernetes.io/scheme` | Gateway annotation `alb.ingress.kubernetes.io/scheme` |
| `alb.ingress.kubernetes.io/certificate-arn` | Gateway listener `tls.certificateRefs` or annotation |
| `alb.ingress.kubernetes.io/actions.*` | HTTPRoute `filters` + `backendRefs` |

**Impact (per Impact Indicator):**
- 🟡 1–2 (Low): All annotations map to HTTPRoute features or Gateway annotations
- 🟠 3–4 (Medium): Most map cleanly, some need AWS service substitution (WAF, Cognito)
- 🔴 5 (High): Heavy use of nginx snippets/lua with no Gateway API equivalent
- ⬜ Unknown: Cannot parse annotations

### 3.2 — TLS Configuration

**What to check:**
- Ingress TLS sections (spec.tls)
- TLS termination strategy
- Certificate sources (K8s Secrets vs ACM)

**How to check:**
1. For each Ingress, check `spec.tls` entries
2. Check for ACM certificate ARN annotations
3. Check for SSL passthrough annotations

**Gateway API TLS model:**
- TLS termination is configured on the **Gateway listener**, not on HTTPRoute
- ACM certificates: referenced via Gateway annotation
- K8s Secret certs: referenced via `tls.certificateRefs` in Gateway listener
- SSL passthrough: use TLSRoute (not HTTPRoute)

**Impact (per Impact Indicator):**
- 🟡 1–2 (Low): Edge termination with ACM — maps directly to Gateway listener
- 🟠 3–4 (Medium): Using K8s Secrets — need cert-manager Gateway integration or migrate to ACM
- 🔴 5 (High): SSL passthrough required — needs TLSRoute (experimental channel CRD)
- ⬜ Unknown: Cannot determine TLS configuration

> **Cutover-risk caveat — the *migration action* is not Low.** Moving the cert store (K8s Secret → ACM) **at the same time as** the routing/class change risks **SSL/TLS handshake failures or downtime** if DNS lags or ACM domain validation hasn't completed. The "if-left-as-is" Impact may be low (the app serves TLS today), but the **remediation step** must be rated ≥ Medium and sequenced: **(1)** request/validate the ACM cert to `ISSUED` first, **(2)** keep the existing NGINX path live, **(3)** switch class / cut over DNS only after the new ALB + cert are verified. Never bundle "migrate TLS to ACM" into a Low/one-step task.

### 3.3 — Backend Service Compatibility

**What to check:**
- All backend services referenced by Ingress resources exist and are healthy
- Service types (ClusterIP preferred for Gateway API with IP target mode)
- Cross-namespace backends (need ReferenceGrant in Gateway API)

**How to check:**
1. For each Ingress, extract backend service references
2. Verify each Service exists with healthy endpoints
3. Flag any cross-namespace references — these need ReferenceGrant resources

**Impact (per Impact Indicator):**
- 🟡 1–2 (Low): All backends healthy, same-namespace, ClusterIP
- 🟠 3–4 (Medium): Some cross-namespace backends (need ReferenceGrant) or NodePort services
- 🔴 5 (High): Missing backends or services with no endpoints
- ⬜ Unknown: Cannot verify endpoint health

**Topology data to collect:** Record every Ingress→backend mapping for the 3D visualization.
