# Report Generation

> **Part of:** [eks-ingress-migration](../SKILL.md)
> **Purpose:** Deterministic scoring algorithm, category weights, classification bands, re-architecture gate logic, severity taxonomy, consistency checks, and the complete markdown report template

---

## Output Contract

One markdown report file per cluster assessed. For multi-cluster runs, also produce a Summary file (see SKILL.md multi-cluster contract).

**Filename pattern:** `EKS-Ingress-Migration-{cluster}-{YYYY-MM-DD}.md`

- `{cluster}` — the EKS cluster name
- `{YYYY-MM-DD}` — assessment date in ISO format

**Examples:**
- `EKS-Ingress-Migration-prod-api-2025-01-15.md`
- `EKS-Ingress-Migration-staging-cluster-2025-03-22.md`

No JSON, HTML, or manifest files are produced. The report is self-contained markdown.

---

## Step 1: Build Master Finding List and Calculate the Migration Difficulty Score

### 1.1 — Build the Master Finding List

Compile ALL findings from the assessment. Every item must appear. No item may be skipped. Each finding carries an **Impact 1-5** (per the Impact Indicator rubric). This list is the single source of truth for the score — every point deducted MUST trace back to exactly one row here.

### 1.2 — What the score means

The **Migration Difficulty Score** is a **0-100** number that reflects the **amount of change / effort** needed to leave NGINX: **high = little change (easy)**, **low = much change (hard)**. It is an *effort index*, not a manday estimate — it ranks relative effort using the per-finding Impact ratings.

Two design rules:

- **The score is NOT artificially capped.** A single hard item no longer locks the whole score at "very hard." Items that genuinely need redesign are surfaced **separately** via the **Re-architecture Gate** (section 1.4) — an informational badge that does not overwrite the number. This lets a mostly-clean estate score well while still flagging the one route that needs a rethink.
- **Clean routes count.** Routes already on a target/maintained controller contribute **0 effort** and stay in the denominator, so "how much is already fine" is visible and pulls the score up.

### 1.3 — Map each finding to a scoring category

Every finding belongs to exactly one category. Categories are weighted by a **max deduction cap** — the cap is how much that dimension can drag down "ease of migration".

**0-effort routes (count, never deduct):** an Ingress/route already served by the **AWS Load Balancer Controller (ALB)**, **Gateway API**, or a **maintained 3rd-party controller that supports the NGINX feature set** is "done". It appears in the inventory denominator at **0 pts** and is **excluded** from the Scale/Volume work-count. Do not deduct for routes that need no migration.

| Category | Max deduction | Findings that feed it |
|----------|--------------|----------------------|
| Feature-Gap — **No Equivalent (Tier A)** | 30 | NGINX features with **no faithful target equivalent and no standard workaround**: `configuration-snippet`/`server-snippet`/Lua, ModSecurity, mirror-to-arbitrary-backend, regex rewrite with capture groups, TLS passthrough, mTLS client-cert. **These also raise the Re-architecture Gate.** |
| Feature-Gap — **Workaround Exists (Tier B)** | 10 | Features with **no native ALB annotation but a well-known low-effort workaround**: **CORS** (app/middleware), **IP allowlist** (Security Group / WAF), **rate-limit** (WAF). Default **Impact 2** when the feature is performance/hardening only; **Impact 3** when it is entangled with business-logic flow (multiple workstreams to coordinate). May score higher (up to 5) when the upstream migration-path reference rates the specific migration complexity as High (e.g., ALB.1 IP allowlist migration rated High in alb-migration.md). The per-feature rating in the migration-path reference takes precedence over this default. |
| Routing Complexity | 20 | Regex paths, `rewrite-target`, canary/traffic-split, header/method routing, cross-namespace fan-out |
| TLS & Certificates | 15 | cert-manager to ACM move, SNI, multi-cert hosts |
| DNS Cutover & Blast Radius | 15 | New ALB endpoint + DNS repoint, external-dns Gateway-API source maturity, hostname/TTL stability |
| Downtime / Rollback Readiness | 10 | New-LB provisioning, long-lived/stateful connections, presence of a weighted/blue-green rollback path |
| Controller Health & EOL/CVE | 10 | NGINX version EOL, active CVE exposure, controller pod health |
| Scale / Volume | 10 | **Count of routes that actually need work** = total routes minus 0-effort routes. Do NOT scale off the raw total. |
| Backend Compatibility | 5 | Exotic backends, `ExternalName`, service-type edge cases |

Caps deliberately sum to 125 (over-provisioned) so a genuinely high-change estate floors toward 0 — that is intended: much change results in a low score.

### 1.4 — Scoring algorithm (deterministic — follow EXACTLY)

```
# Per-finding base points by Impact (reuse the rating already assigned)
def base_points(impact):
    return {5: 10, 4: 6, 3: 4, 2: 2, 1: 1}[impact]   # Unknown = 0 pts, but list it

# Tier-B feature impact (CORS / IP-allowlist / rate-limit):
#   Default Impact 2 if performance/hardening only (not in the business-logic path)
#   Default Impact 3 if entangled with business-logic flow (multiple workstreams)
#   May score up to Impact 5 when the migration-path reference (e.g. alb-migration.md)
#   rates the specific feature's migration complexity as High.

# 0-effort routes (already on ALB / Gateway API / supported 3rd-party):
#   list them in the inventory, contribute 0 pts, EXCLUDE from Scale/Volume count.

score = 100
for each category:
    cat_deduction = 0
    for each finding in this category:        # 0-effort routes contribute nothing
        cat_deduction += base_points(finding.impact)
    cat_deduction = min(cat_deduction, category_cap)
    score -= cat_deduction
score = max(0, score)

# --- Re-architecture Gate (INFORMATIONAL — does NOT change the score) ---
# Count the routes/conditions that need a redesign or approval. Report this as a
# separate badge next to the score. The score already reflects their effort via the
# Tier-A / TLS / cross-namespace deductions — do NOT also cap the number.
gate = 0
gate += count(production routes using a Tier-A no-workaround feature: Lua/snippet/mirror/regex-capture)
gate += count(routes needing TLS passthrough OR mTLS client-cert with no faithful target)
gate += count(cross-namespace / shared-LB routes not expressible without ownership changes)
gate += 1 if a revenue-critical hostname cutover has no rollback path (single hostname, no weighted/blue-green)
gate += 1 if controller is EOL with an active exploitable CVE and no maintenance window
gate += 1 if EKS Auto Mode managed LB and a self-managed AWS LB Controller race for ownership
# gate == 0  -> "No re-architecture blockers"
# gate  > 0  -> "N route(s)/condition(s) need redesign or approval"
```

### 1.5 — Score interpretation

| Score | Label | Meaning |
|-------|-------|---------|
| 90-100 | **TRIVIAL** | Mechanical — ALB Controller / ATX auto-converts; hours |
| 80-89 | **EASY** | Minor manual tweaks |
| 70-79 | **MODERATE** | Several features need manual mapping; plan it |
| 60-69 | **HARD** | Significant feature gaps or risky cutover |
| 0-59 | **VERY HARD** | Large amount of change across the estate |

The **Re-architecture Gate** is reported independently of the band: e.g. *"82 / EASY — 1 route needs redesign"* is valid — the estate is mostly trivial, but one route still needs a rethink. Score answers "how much work?"; the gate answers "does anything need a redesign decision?".

### 1.6 — Build the Score Breakdown table (MANDATORY)

Before writing the headline, produce this table so the math is auditable. Sum `base_points` per category, apply the cap, order highest-deduction first. The **Total** must equal `100 - score`. Add a final **Re-architecture Gate** line stating the count and which routes (it does not change the total).

```
| Category | Findings (impact) | Raw pts | Capped | Cap |
|----------|-------------------|---------|--------|-----|
| Feature-Gap — No Equivalent (Tier A) | snippet on /checkout (5) | 10 | 10 | 30 |
| Feature-Gap — Workaround Exists (Tier B) | CORS (5), rate-limit (5), allowlist (5) | 30 | 10 | 10 |
| ... | ... | ... | ... | ... |
| **Total deductions** | | | **-XX** | |
| **Re-architecture Gate** | 1 route — snippet on /checkout | — | — | — |
```

Then: `Score = 100 - (total capped deductions) = XX — [LABEL]`, plus the gate badge.

### 1.7 — Worked example

Estate: **18 ingresses** — **6 already on ALB** (0 effort, done), **2 annotation-only** moves, and **10 needing work**. Of the 10: `configuration-snippet` Lua on `/checkout` (Tier A, no workaround), CORS + rate-limit + IP-allowlist (all Impact 5 per alb-migration.md — ALB migration-path rates these High), `rewrite-target` on 3 routes (Routing, Impact 2 each = annotation-grade), cert-manager to ACM (TLS, Impact 3), NGINX 1.9.x EOL no active CVE (Controller, Impact 3).

```
Feature-Gap Tier A:  10  (cap 30)   # /checkout snippet  -> also Gate +1
Feature-Gap Tier B:  30  (cap 10)   # CORS+rate-limit+allowlist, Impact 5 each per alb-migration.md
Routing:              6  (cap 20)   # 3 rewrites @ Impact 2 + 2 annotation-only moves
TLS:                  4  (cap 15)   # cert-manager -> ACM
Controller:           4  (cap 10)   # nginx EOL, no CVE
Scale/Volume:         4  (cap 10)   # 10 routes need work (NOT 18) -> Impact 3
Total = 38  ->  score = 100 - 38 = 62  (HARD)

Re-architecture Gate = 1  ->  "1 route needs redesign (snippet on /checkout)"
```

Final: **62 / HARD — 1 route needs redesign.** The model credits the 6 done + 2 easy routes, rates CORS/allowlist/rate-limit at Impact 5 per alb-migration.md (capped at 10 for the Tier-B category), counts 10 (not 18) for volume, and reports the one true blocker as a gate instead of erasing the number.

> **Note:** The Tier-B default Impact 2/3 applies to features that the migration-path reference does not explicitly rate.

---

## Step 2: Consistency Checks (MANDATORY)

Run these checks before finalizing the report. Fix any failures in-place.

| Check | Fix |
|-------|-----|
| High-impact (5) item missing from Blockers table | Add it |
| Medium-impact item missing from Recommendations table | Add it |
| Executive Summary mentions wrong rating | Fix to match master list |
| Prose paragraph that should be a table | Convert to table |
| Raw YAML in findings (not Migration Approach) | Replace with summary |
| Score Breakdown total does not equal (100 - score) | Recompute — the table is the source of truth |
| CORS / IP-allowlist / rate-limit scored above default Impact 3 without migration-path reference justification | Re-rate to default (2 or 3), OR cite the migration-path reference rating that justifies the higher score |
| Routes already on ALB / Gateway API counted as work | Set to 0 effort; exclude from Scale/Volume count |
| Scale/Volume scored off the raw total, not routes-needing-work | Recount excluding 0-effort routes |
| Re-architecture Gate count does not equal Tier-A/passthrough/ownership findings | Reconcile the gate to the master list |
| Score band label does not match the section 1.5 table | Fix the label to match the number |

---

## Step 3: Write the Markdown Report

Generate the following report structure. Use tables for all structured data. No prose lists where a table fits.

### Content Rules (MANDATORY)

1. **Use tables for all structured data.** Never write lists of facts as prose.
2. **No ID column in any table.** Remove all "ID" columns — they add no value.
3. **No raw YAML/config in findings.** YAML belongs only in Migration Approach examples.
4. **Every finding cell: max 2 sentences.**
5. **No filler text.** Go straight to content.
6. **One Migration Difficulty Score (0-100), derived only from the rated findings.** It is a deterministic roll-up of the per-finding Impact ratings (see Step 1), shown once — not a separate prescriptive verdict. The migration-path decision still belongs to the team. Do NOT invent ad-hoc per-section sub-scores.
7. **Multi-value cells in tables:** put each item on its own line using `<br>`. For **Current Configuration**, use nested bullet/sub-bullet lists instead of a table.
8. **Executive Summary = one-shot understanding for a non-technical reader.** Top-level bullet per impact theme, indented sub-bullets for specifics. Bold the key term in each bullet.
9. **Emphasis syntax:** `**bold**` for key terms, backticks for `versions/code`. Use sparingly — only words that carry the impact.
10. **Lead with impact.** Order Executive Summary bullets and Assessment Summary rows from highest impact to lowest.
11. **Impact everywhere, by the rubric:** Assessment Summary, Ingress Discovery, Routing Topology, Traffic & Routing, Blockers, Recommendations, Ingress Resource Analysis, DNS & Certificates Analysis, Migration Risk all use the **Impact 1-5** scale (1-2 Low / 3-4 Medium / 5 High) — never GREEN/AMBER/RED. Every score MUST be justified against the **Impact Indicator** rubric (security/reputation, business/revenue, nature & effort), not ad-hoc judgement.
12. **Execution risk counts — do NOT score by YAML-edit size.** A small manifest change can still be high-impact. Specifically: changing `ingressClassName` to a *different controller* provisions a brand-new load balancer and only takes traffic after a DNS cutover; moving a feature that has no faithful equivalent to WAF/app usually needs application/code changes; and any TLS/cert-store change done together with routing changes risks SSL handshake errors / downtime. Score by operational risk, not diff size.

---

## Complete Report Template

Generate the following structure. Replace placeholders with assessment data.

```markdown
# EKS Ingress Migration Assessment Report

| Information | Value |
|-------------|-------|
| Cluster | {cluster_name} |
| Region | {region} |
| Kubernetes Version | {version} |
| Account ID | {account_id} |
| Assessment Date | {YYYY-MM-DD HH:MM} |

---

## Migration Difficulty Score

> **{score}/100 — {LABEL}**

{One sentence: how much change leaving NGINX needs for this cluster and the single biggest driver. State how many routes are already done (0 effort) and how many actually need work.}

{If gate > 0:}
> **Re-architecture Gate:** {N} route(s)/condition(s) need redesign — {list which routes/conditions}

{If gate == 0:}
> **Re-architecture Gate:** No re-architecture blockers identified.

### Score Breakdown

| Category | Findings (impact) | Deduction | Cap |
|----------|-------------------|-----------|-----|
| {highest-deduction category} | {finding (impact), ...} | -{X} pts | {cap} |
| {next category} | {...} | -{X} pts | {cap} |
| ... | ... | ... | ... |
| **Total deductions** | | **-{X} pts** | **Score: {score} — {LABEL}** |
| **Re-architecture Gate** | {N route(s) + which, or "none"} | — | informational |

> The gate row never changes the total — it flags routes that need a redesign/approval decision. Routes already on ALB / Gateway API / a supported 3rd-party controller are listed at **0 pts** and excluded from the Scale/Volume count.

---

## Executive Summary

> Write for a non-technical reader — one glance must answer "how risky is this and why." Lead with the biggest impact. **Bold** the key noun in each bullet. Split any bullet that lists multiple items into indented sub-bullets.

- **Ingress controllers:** {N} in use — {the single biggest risk, e.g. one is End-of-Life with known CVEs}
  - {Controller A} `vX` (modern)
  - {Controller B} `vX` (EOL / unsupported)
- **Biggest migration blocker:** {the one thing most preventing a clean migration} — {one phrase why}
- **Conversion effort:** {N} Ingress resources — {X} convert cleanly, {Y} need redesign ({features with no Gateway API equivalent})
- **Scope:** {namespaces} namespaces, {hosts} hosts, TLS {partial — X of Y}

---

## Impact Indicator

> This rubric governs EVERY Impact score in the report. Impact weighs three dimensions: security/reputation, business/revenue, and nature & effort to remediate; score the dominant one.

| Impact | Meaning |
|--------|---------|
| 1-2 Low | **Security:** hardening gap, no business-effective breach. **Business:** no revenue loss / downtime. **Nature:** optional best practice. **Effort:** hours to 1 day, one person, single service or route. |
| 3-4 Medium | **Security:** breach with limited reputation loss. **Business:** revenue loss limited to short downtime. **Nature:** tech debt, hard to reverse. **Effort:** scoped to one area or cluster. |
| 5 High | **Security:** breach with major loss or reputational damage. **Business:** significant revenue loss or prolonged downtime. **Nature:** needs re-design / re-architecture, maybe business or provider approval. If large but straightforward to deploy, rate medium-to-low. |

---

## Assessment Summary

> Rate each theme by **migration Impact 1-5**, highest first. Impact = how hard/risky it is to transfer or replace that feature versus the current NGINX/Ingress setup. Do NOT rate trivial prerequisites — rate the feature transfer/replacement difficulty.

| Theme | Impact | Why — feature transfer / replacement effort vs. current setup |
|-------|--------|----------------------------------------------------------------|
| {highest-impact theme} | 5 High | {which feature cannot transfer cleanly + replacement effort} |
| {next} | 4 Medium | {...} |
| {next} | 3 Medium | {...} |
| {next} | 2 Low | {...} |
| {lowest} | 1 Low | {...} |

---

## Current Configuration

> Convey the environment at a glance. Use a bullet list with sub-bullets for multi-value items.

- **Ingress controllers:**
  - {controller-a} `vX` (modern)
  - {controller-b} `vX` (EOL)
- **Controller namespaces:**
  - {ns1}
  - {ns2}
- **Total Ingress resources:** {count}
- **Namespaces with Ingress:**
  - {ns1}
  - {ns2}
- **Routing pattern:** {host-based / path-based / both}
- **TLS enabled:** {partial — X of Y}
- **Load balancer types:** {ALB / NLB / ClusterIP}
- **Nodes:** {count} — {instance types}

---

## Ingress Discovery

| Item | Impact | Current State | Recommendation |
|------|--------|---------------|----------------|
| Ingress Controllers Installed | {1-5} | {summary} | {action or "None required"} |
| IngressClass Resources | {1-5} | {summary} | {action or "None required"} |
| Ingress Resource Inventory | {1-5} | {summary} | {action or "None required"} |

---

## Routing Topology

> Per-route line items. Combine host+path into one Route column, backend+port into Backend:Port, TLS as yes/no, and add a per-route Impact (1-5). Omit a shared host suffix (note it above the table).

| Ingress | NS | Controller | Route (host / path) | Backend:Port | TLS | Impact |
|---------|----|------------|---------------------|--------------|-----|--------|
| {name} | {ns} | {controller} | {host / path} | {svc:port} | {yes/no} | {1-5} |

---

## Traffic & Routing

| Item | Impact | Current Config | Recommendation |
|------|--------|----------------|----------------|
| Routing Pattern Mapping | {1-5} | {summary of current routing} | {action} |
| Advanced Traffic Features | {1-5} | {features in use} | {action} |
| Cross-Namespace Routing | {1-5} | {current state} | {action} |

---

## Migration Options

> Three migration paths. Every option uses the same layout: an info panel (blockquote) followed by Phase 1-4 tables.

### Option 1: Gateway API

> **What:** Kubernetes-native successor to Ingress (HTTPRoute + Gateway). **Effort:** Medium. **Best when:** you want the long-term standard.
> **Caveats:** L7 ALB Gateway API support is recent (HTTPRoute v2.14+) — verify TLS handling and routing filters per route before cutover. On EKS Auto Mode running a self-managed LBC too, scope GatewayClass/IngressClass per controller to avoid load-balancer ownership conflicts.

#### Phase 1 — Foundation
| Step | Action |
|------|--------|
| 1 | Install Gateway API CRDs |
| 2 | Verify/upgrade AWS LB Controller (v2.14+ for L7 Gateway API; not needed on Auto Mode) |
| 3 | Create GatewayClass |
| 4 | Create Gateway per listener group |

#### Phase 2 — Convert & Test
| Step | Action |
|------|--------|
| 1 | Generate HTTPRoutes from current Ingress |
| 2 | Apply low-risk routes first; validate routing, TLS, health |
| 3 | Routes with no equivalent (snippets/auth/mirror) — redesign (see Blockers) |

#### Phase 3 — Cutover
| Step | Action |
|------|--------|
| 1 | Shift DNS to the Gateway ALB (weighted) |
| 2 | Monitor 5xx / latency |
| 3 | Confirm all HTTPRoutes Accepted=True |

#### Phase 4 — Cleanup
| Step | Action |
|------|--------|
| 1 | Delete migrated Ingress resources |
| 2 | Remove old controllers |
| 3 | Remove unused IngressClasses |

---

### Option 2: AWS Load Balancer Controller (ALB Ingress)

> **What:** Stay on the Ingress API but swap NGINX annotations for ALB annotations. Gets WAF, Cognito/OIDC, Shield integration. **Effort:** Low-Medium. **Best when:** team not ready for Gateway API, needs ALB features immediately, or has many Ingress resources to convert quickly.

#### Annotation Conversion Summary

| NGINX Annotation | ALB Equivalent |
|-----------------|----------------|
| `ingressClassName: nginx` | `ingressClassName: alb` |
| `nginx...rewrite-target: /$2` | `alb...transforms.<svc>` (url-rewrite JSON) |
| `spec.tls[].secretName` | `alb...certificate-arn` or `certificate-discovery: "true"` |
| `nginx...ssl-redirect: "true"` | `alb...ssl-redirect: "443"` |
| `nginx...proxy-read-timeout` | `alb...load-balancer-attributes: idle_timeout.timeout_seconds=N` |
| `nginx...auth-url` | `alb...auth-type: oidc` + `auth-idp-oidc` JSON |
| `nginx...enable-cors` | Remove — use AWS WAF or app-level |
| `nginx...whitelist-source-range` | `alb...scheme: internal` + security groups |
| `nginx...proxy-body-size` | Remove — app-level config |

#### Phase 1 — Foundation
| Step | Action |
|------|--------|
| 1 | Install AWS LB Controller v2.7.2+ (not needed on EKS Auto Mode) |
| 2 | Provision ACM certificates |

#### Phase 2 — Convert & Test
| Step | Action |
|------|--------|
| 1 | Convert annotations per mapping above |
| 2 | Deploy migrated Ingress (new ALB created) |
| 3 | Validate routing, TLS termination, health checks |

#### Phase 3 — Cutover
| Step | Action |
|------|--------|
| 1 | DNS weighted routing: shift traffic old LB to new ALB |
| 2 | Monitor error rates |
| 3 | Confirm all routes healthy |

#### Phase 4 — Cleanup
| Step | Action |
|------|--------|
| 1 | Delete old NGINX Ingress resources |
| 2 | Remove NGINX controller |
| 3 | Remove unused TLS Secrets |

#### Per-Ingress Conversion Table

| Ingress | Namespace | Key Changes | Complexity |
|---------|-----------|-------------|-----------|
| {name} | {ns} | {e.g., "rewrite to transforms, TLS to ACM"} | {Low/Medium/High} |

---

### Option 3: AWS Transform (ATX) — Automated

> **What:** Fully automated manifest rewriting for customers with AWS Transform access. ATX reads a Transform Definition and converts all NGINX Ingress manifests to ALB annotations automatically. **Effort:** Low. **Best when:** many Ingress resources (>10), want consistent automated output, have ATX workspace access.

#### Phase 1 — Foundation
| Step | Action |
|------|--------|
| 1 | Upload the NGINX-to-ALB Transform Definition to the ATX workspace (defines annotation mapping rules, TLS conversion, and rewrite transforms — see [AWS Transform documentation](https://docs.aws.amazon.com/transform/latest/userguide/) for TD authoring and upload steps) |
| 2 | Point ATX at Ingress manifest repository |

#### Phase 2 — Convert & Test
| Step | Action |
|------|--------|
| 1 | ATX scans, converts, validates automatically |
| 2 | Review diff output |

#### Phase 3 — Cutover
| Step | Action |
|------|--------|
| 1 | Apply converted manifests |
| 2 | DNS cutover to new ALB |
| 3 | Monitor error rates |

#### Phase 4 — Cleanup
| Step | Action |
|------|--------|
| 1 | Delete old NGINX controller |
| 2 | Remove orphaned resources |

#### What ATX Converts

| Pattern | Before (NGINX) | After (ALB) |
|---------|----------------|-------------|
| IngressClass | `nginx` | `alb` |
| URI Rewrite | `rewrite-target` + regex | `transforms.<svc>` JSON |
| TLS | K8s Secrets | ACM `certificate-arn` |
| Auth | `auth-url` | `auth-type: oidc` |
| CORS | `enable-cors` | Removed (WAF/app) |
| Internal | `whitelist-source-range` | `scheme: internal` |

---

## Blockers

> Impact 1-5. **Action Required** is a bullet list. No Effort column.

| Finding | Impact | Action Required |
|---------|--------|-----------------|
| {finding name} | {5 High} | - {action}<br>  - {sub-action} |

> If no high-impact items exist, write: "No blockers identified."

---

## Recommendations

> Impact 1-5 = how disruptive *implementing* the action is to the running app / production.

| Finding | Action | Priority | Impact |
|---------|--------|----------|--------|
| {finding name} | {specific action} | {High/Medium/Low} | {1-5} |

---

## Ingress Resource Analysis

> Impact 1-5 = severity if left as-is (not migrated).

| Item | Impact | Current State | Recommendation |
|------|--------|---------------|----------------|
| Annotation Inventory & Mapping | {1-5} | {summary} | - {action}<br>  - {sub-action} |
| TLS Configuration | {1-5} | {summary} | - {action} |
| Backend Service Compatibility | {1-5} | {summary} | - {action} |

---

## DNS & Certificates Analysis

| Item | Impact | Current State | Recommendation |
|------|--------|---------------|----------------|
| external-dns Gateway API Support | {1-5} | {summary} | - {action} |
| cert-manager Gateway Integration | {1-5} | {summary} | - {action} |
| ACM Integration | {1-5} | {summary} | - {action} |

---

## Migration Risk

| Item | Impact | Current State | Recommendation |
|------|--------|---------------|----------------|
| Downtime Risk | {1-5} | {summary} | - {action} |
| Feature Gap Analysis | {1-5} | {summary} | - {action} |
| Rollback Readiness | {1-5} | {summary} | - {action} |

---

## AWS Reference Links

| Topic | URL |
|-------|-----|
| AWS Load Balancer Controller | https://kubernetes-sigs.github.io/aws-load-balancer-controller/ |
| Gateway API Specification | https://gateway-api.sigs.k8s.io/ |
| HTTPRoute API Reference | https://gateway-api.sigs.k8s.io/reference/api-types/httproute/ |
| Gateway API Migration Guide | https://gateway-api.sigs.k8s.io/guides/getting-started/migrating-from-ingress/ |
| external-dns Gateway API | https://kubernetes-sigs.github.io/external-dns/latest/docs/sources/gateway-api/ |
| cert-manager Gateway API | https://cert-manager.io/docs/usage/gateway/ |
| EKS Best Practices | https://docs.aws.amazon.com/eks/latest/best-practices/ |
| EKS User Guide | https://docs.aws.amazon.com/eks/latest/userguide/ |
| AWS Transform User Guide | https://docs.aws.amazon.com/transform/latest/userguide/ |

Do NOT fabricate URLs beyond this list.

---

*This report was generated by an AWS DevOps Agent skill provided as sample code for educational
and demonstration purposes only. Findings should be reviewed and validated before
acting on them. See the project's README and LICENSE for full terms.*
```

---

## Section Placement

The report sections map to these logical groups:

| Group | Sections |
|-------|----------|
| **Overview** | Cluster info table, Migration Difficulty Score + Score Breakdown, Executive Summary, Impact Indicator |
| **Assessment Summary** | Assessment Summary table (Impact-ordered), Current Configuration, Ingress Discovery |
| **Routing Topology** | Routing Topology table, Traffic & Routing |
| **Migration Approach** | Migration Options (Gateway API, ALB, ATX — consistent panels), Blockers, Recommendations |
| **Analysis** | Ingress Resource Analysis, DNS & Certificates Analysis, Migration Risk |
| **References** | AWS Reference Links |

---

## Recommendation Sort Order

Recommendations are sorted by:

1. **Impact** (descending): 5 High, then 4-3 Medium, then 2-1 Low
2. **Priority** (descending within each impact level): High, Medium, Low
