# DNS & Certificate Management

> **Rating model:** Express every finding as **Impact 0–5** using the *Impact Indicator* rubric, weighing three dimensions **in priority order: (1) business logic / revenue — the live traffic at stake · (2) security / reputation · (3) effort to remediate**. **Effort is NOT a severity driver** — a fix being easy or hard never moves the score (it depends on who implements it). **Presence is decided by estate state** — absent controller / empty estate / orphaned dead config = **non-event (0)**; a broken controller is **tech debt (1)** with zero bound routes or a **suspected active outage** (flagged outside the score) with bound routes; a running controller with a **control-plane CVE counts even at zero routes**. See `ingress-discovery.md` for the full presence/stacking rules. Band mapping is a starting point — 🟢 0 / 🟡 1–2 / 🟠 3–4 / 🔴 5 — but the Impact Indicator criteria set the final score (e.g. an easy-to-deploy prerequisite stays 🟡 low even if it blocks a path). All checks are **read-only** (`kubectl get/describe`, `aws … describe/list`).


## Purpose
Assess DNS automation and TLS certificate management for Gateway API migration.

## Checks to Execute

### 4.1 — external-dns Gateway API Support

**What to check:**
- external-dns Deployment installed
- Source configuration — **must include `gateway-httproute`** for Gateway API migration
- IRSA/Pod Identity for Route 53 access

**How to check:**
1. List Deployments → filter for `external-dns`
2. Check container args for `--source=` values
3. Check ServiceAccount for IRSA annotation

**Critical:** external-dns must be configured with `--source=gateway-httproute` (and optionally `--source=gateway-grpcroute`) to auto-manage DNS for Gateway API resources. If only `--source=ingress` is set, DNS won't work after migration.

**Impact (per Impact Indicator):**
- 🟡 1–2 (Low): external-dns installed with `gateway-httproute` source, IRSA configured
- 🟠 3–4 (Medium): external-dns installed but only `ingress` source — needs config update
- 🔴 5 (High): No external-dns — DNS records managed manually
- ⬜ Unknown: Cannot determine DNS management

### 4.2 — cert-manager Gateway API Integration

**What to check:**
- cert-manager installed and healthy
- Gateway API integration enabled (cert-manager v1.15+ has native Gateway API support)
- ClusterIssuer/Issuer configured

**How to check:**
1. List Deployments → filter for `cert-manager`
2. Check cert-manager version (v1.15+ for Gateway API)
3. Check for `--feature-gates=ExperimentalGatewayAPISupport=true` in controller args (pre-v1.15)
4. List ClusterIssuers → check solver type

**Impact (per Impact Indicator):**
- 🟡 1–2 (Low): cert-manager v1.15+ with Gateway API support, ClusterIssuer ready
- 🟠 3–4 (Medium): cert-manager installed but Gateway API feature gate not enabled, or older version
- 🔴 5 (High): No cert-manager and TLS certs are static K8s Secrets
- ⬜ Unknown: Cannot determine cert management

### 4.3 — ACM Integration

**What to check:**
- Current Ingress resources using ACM certificate ARNs
- ACM certificates available in the account/region
- Gateway API ACM model: certificates referenced on Gateway listener via annotation

**How to check:**
1. Scan Ingress annotations for `alb.ingress.kubernetes.io/certificate-arn`
2. Extract unique ACM ARNs
3. Verify certificates exist and are valid

**Impact (per Impact Indicator):**
- 🟡 1–2 (Low): Using ACM certificates — maps directly to Gateway listener annotations
- 🟠 3–4 (Medium): Mix of ACM and K8s Secret certificates
- 🔴 5 (High): No ACM — all self-managed Secrets
- ⬜ Unknown: Cannot verify ACM certificate status
