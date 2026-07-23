---
title: "Report Generation"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-ingress-migration/references/report-generation.md
format: md
---

:::info[Source]
This page is generated from [skills/eks-ingress-migration/references/report-generation.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-ingress-migration/references/report-generation.md). Edit the source, not this page.
:::

# Report Generation

## Purpose

Generate dual-format assessment report matching the 5-section navigation structure:
**Overview → Assessment Summary → Routing Topology → Migration Approach → Analysis**

This is an **assessment report** — present findings and options, do not prescribe a single migration path.

## Step 1: Build Master Finding List & Calculate the Migration Difficulty Score

### 1.0 — Empty-estate & orphaned-config short-circuit (CHECK THIS FIRST)

Before scoring anything, decide whether there is a live estate to migrate at all. **A high score is correct when there is little/nothing to migrate — the number measures change required, not cluster wealth.**

**A) Truly empty estate** — no ingress controller **AND** no IngressClass **AND** no Ingress resources (this case **also** applies when the only controller present is a healthy migration-*target* controller — e.g. AWS LB Controller — with nothing bound to migrate, **and that controller is not CVE/EOL-affected**):
- **Security gate (check BEFORE short-circuiting):** if the only-present controller is on a **known-CVE / EOL version** (e.g. ingress-nginx `< v1.11.5 / < v1.12.1` with the admission webhook exposed — see `ingress-discovery.md` §1.4), it is a **security finding regardless of route count** (control-plane exposure survives zero routes). **Do NOT short-circuit** in that case — run `ingress-discovery.md` §1.4, score the security dimension, and record it against the Re-architecture Gate's **EOL-CVE / control-plane-RCE condition line** (§1.4 *Scoring algorithm*, this file). That is a non-route **condition**, **not** a route — so it raises the gate legitimately with **zero** route findings and must **not** be rendered as a phantom `⛔ N routes` (the badge reads `⛔ N route(s)/condition(s)`). The short-circuit below is only for a controller that is both healthy **and** not vulnerable.
- **Score = 100 / TRIVIAL, labelled "N/A — nothing to migrate". Stop the deduction math.** This short-circuit **replaces §1.1–1.6** — there are no findings to deduct, so do not run the deep category machinery. (The Score Breakdown table may still render with all-zero rows for transparency.)
- Emit a plain note next to the score, e.g.: *"No ingress controller, IngressClass, or Ingress resources are present, so there is nothing to migrate. **Absence is not the same as health** — if you expected an ingress estate here, confirm it was not accidentally removed. (Cluster/node upgrades are out of scope for this skill and are not counted as migration.)"*
- **Precedence:** if sections 4–5 surface DNS/certificate items, note that with **no Ingress present there is nothing to cut over**, so they are listed at **0** (non-events) and do not pull the score below 100.
- Still render the standard report shell (Overview, score gauge, this note); the deep-dive sections simply report "none found".

**B) Orphaned config** — Ingress resources exist **but no controller for their class is installed** (dead blueprints, no road). This is judged **per class**: orphans of class `X` with **no class-`X` controller** are Case B **even if a different, healthy controller** (e.g. AWS LBC serving `alb`-class routes) is present — score the class-`X` orphans **0** and let the live controller's own routes produce the headline (this is the "other live findings exist" path below, not a fixed 100):
- **Verify before you downgrade (conservative default).** "Zero live traffic" must be *evidenced*, not assumed from the missing controller. For **alb-class** orphans especially, a previously-provisioned **ALB/NLB keeps forwarding to registered targets even after the controller is uninstalled** (deletion requires the controller to process the `ingress.k8s.aws/resources` finalizer). **First identify *which* ALB belongs to each orphaned Ingress** — read the Ingress's `status.loadBalancer.ingress[].hostname` (the provisioned ALB DNS name); if status is empty, find the LB by its controller tags: `aws elbv2 describe-load-balancers`, then `aws elbv2 describe-tags --resource-arns <lb-arns>` matching `ingress.k8s.aws/stack=<namespace>/<ingress-name>` (and `elbv2.k8s.aws/cluster=<cluster>`). Then check that specific LB's surviving state — `aws elbv2 describe-target-health --target-group-arn <arn>` for registered/healthy targets, plus its request metrics — before calling the orphan dead. On a multi-ALB account this identification step is **required**: without it you cannot tell which LB to verify. **If you cannot identify the LB or verify zero traffic, treat the estate as live** — it is then a live finding, not a non-event, and the headline comes from that finding.
- Once verified dead: the **absent controller is a non-event (0)** and the orphaned Ingress objects are **also 0** — they carry **zero live traffic**, so there is no live migration work (no traffic to reroute, no downtime risk). The score is **not** dragged down by them.
- If there are *no other live findings*, the estate scores **100 / TRIVIAL**. **If other live findings exist** (e.g. a second, live controller serving traffic, or an unverified/serving orphan ALB), the orphaned config stays 0 but the **headline is whatever those live findings produce** — do **not** assert 100 in that case.
- **Precedence (same as case A):** if sections 4–5 surface DNS/certificate items, note that with **no controller to cut over to there is nothing to migrate**, so they are listed at **0** (non-events) and do not pull the score below the headline (e.g. "no external-dns" is not a deduction on a dead/absent estate).
- Emit the **Migration Crew Alert** note below, substituting the real values: `{N}` = count, `{CONTROLLER_CLASS}` = the orphaned objects' class (nginx/traefik/…), `{SCORE}`/`{LABEL}` = the actual headline. (Only the empty-estate case A is a fixed 100 / TRIVIAL.)

> **Migration Crew Alert: {N} Orphaned Ingress Objects Detected**
> **Finding:** {N} `{CONTROLLER_CLASS}` Ingress objects exist in the cluster, but no matching `{CONTROLLER_CLASS}` ingress controller is installed to serve them.
> **Status:** Dead configuration — inactive routing rules with **no matching controller** to serve them. *(Confirm zero live traffic first — for alb-class objects a previously-provisioned ALB may still be forwarding; see the verify step above. If traffic is unverified, treat as live, not dead.)*
> **Action taken:** Scored **0** (no live migration effort — no traffic to reroute, no downtime risk); the estate's headline is **{SCORE} / {LABEL}**.
> **Recommendation:** Verify whether this is mid-migration debris from an unfinished project. **Before deleting, export/back up these manifests** — they are often the only surviving record of routing intent (see **Export Materials** / the `[[DL:current]]` button) — and confirm they are not awaiting re-adoption by a controller about to be installed. Once confirmed abandoned, clean them up before installing the new controller so it does not adopt unintended routes.

> **Distinction — broken ≠ absent:** if a controller **is present but broken** (CrashLoopBackOff/unreachable), that is **not** case A/B. Handle it per `ingress-discovery.md` §1.1's split: **with bound routes → suspected active outage**, flagged urgently and **outside** the 0–100 score; **with zero bound routes → −1 tech-debt** deduction + cleanup note. In **both** cases the broken controller's routes remain **migratable config** — the migration will resurrect them — so their config complexity is scored normally as migration difficulty (see `ingress-discovery.md` §1.3/§1.4). The tech-debt −1 (or the outage flag) is the operational-hygiene signal, **separate** from that migration-difficulty scoring.

### 1.1 — Build the Master Finding List

Compile ALL scoring findings from sections 1–5 (Ingress Discovery, Traffic & Routing, Ingress Resource Analysis, DNS & Certificates, Migration Risk). Every such item must appear. No item may be skipped. Each finding already carries an **Impact 0–5** (per the Impact Indicator rubric). This list is the single source of truth for the score — every point deducted MUST trace back to exactly one row here.

> **Quarantine — §7.1–7.3 are NOT scored.** The migration-plan checks (§7.1 scope · §7.2 conversion complexity · §7.3 timeline) are **planning outputs**: they restate what sections 1–5 already scored (scope↔Scale/Volume, complexity↔Feature-Gap/Routing) and feed the phased plan and Blockers, **not** the Score Breakdown. **Never add a §7.x row to the Score Breakdown** (that would double-count), and **timeline/duration never carries an Impact score** at all.

### 1.2 — What the score means

The **Migration Difficulty Score** is a **0–100** number that reflects the **amount of change** needed to leave NGINX: **high = little change (easy)**, **low = much change (hard)**. It is **not** a manday estimate and **not** a remediation-effort index — we cannot know who implements it, and the same change is trivial for an expert yet hard for a novice. Instead it rolls up the per-finding **Impact** ratings, which are weighted **business-first, then security, and never by how hard a fix is** (see the Impact Indicator). So the score ranks *how much of the estate must change*, prioritised by what that change protects (revenue/live traffic > security > everything else).

Two design rules from operator feedback drive this version:

- **The score is NOT artificially capped.** A single hard item no longer locks the whole score at "very hard." Items that genuinely need redesign are surfaced **separately** via the **Re-architecture Gate** (§1.4) — an informational badge that does not overwrite the number. This lets a mostly-clean estate score well while still flagging the one route that needs a rethink.
- **Clean routes count.** Routes already on a target/maintained controller contribute **0 effort** and stay in the denominator, so "how much is already fine" is visible and pulls the score up.

### 1.3 — Map each finding to a scoring category

Every finding belongs to exactly one category. Categories are weighted by a **max deduction cap** — the cap is how much that dimension can drag down "ease of migration".

**0-effort routes (count, never deduct):** an Ingress/route already served by the **AWS Load Balancer Controller (ALB)**, **Gateway API**, or a **maintained 3rd-party controller that supports the NGINX feature set** is "done". It appears in the inventory denominator at **0 pts** and is **excluded** from the Scale/Volume work-count. Do not deduct for routes that need no migration.

| Category | Max deduction | Findings that feed it (source sections) |
|----------|--------------|-----------------------------------------|
| Feature-Gap — **No Equivalent (Tier A)** | 30 | NGINX features with **no faithful target equivalent and no standard workaround**: `configuration-snippet`/`server-snippet`/Lua, ModSecurity, mirror-to-arbitrary-backend, regex rewrite with capture groups, TLS passthrough, mTLS client-cert. **These also raise the Re-architecture Gate.** (Ingress Resource Analysis, Traffic & Routing, Blockers) |
| Feature-Gap — **Workaround Exists (Tier B)** | 10 | Features with **no native ALB annotation but a well-known low-effort workaround**: **CORS** (app/middleware), **IP allowlist** (Security Group / WAF), **rate-limit** (WAF). Rate **Impact 2** when the feature is performance/hardening only; **Impact 3** when it is entangled with business-logic flow (multiple workstreams to coordinate). Never Impact 4–5. (Ingress Resource Analysis, Traffic & Routing) |
| Routing Complexity | 20 | Regex paths, `rewrite-target`, canary/traffic-split, header/method routing, cross-namespace fan-out (Traffic & Routing, Routing Topology) |
| TLS & Certificates | 15 | cert-manager→ACM move, SNI, multi-cert hosts (DNS & Certificates Analysis) |
| DNS Cutover & Blast Radius | 15 | New ALB endpoint + DNS repoint, external-dns Gateway-API source maturity, hostname/TTL stability (DNS & Certificates Analysis, Migration Risk) |
| Downtime / Rollback Readiness | 10 | New-LB provisioning, long-lived/stateful connections, presence of a weighted/blue-green rollback path (Migration Risk) |
| Controller Health & EOL/CVE | 10 | Controller pod health + version EOL/CVE (Ingress Discovery §1.1, §1.4). **Absent controller = 0** (non-event). **Present-but-broken with zero bound routes = 1 (tech debt)** — a separate hygiene deduction with a mandatory cleanup note; **broken with bound routes = active outage**, flagged urgently and scored **outside** this 0–100 model. Neither replaces the migration-difficulty of that controller's config. **EOL/CVE: data-plane severity scales with the live business traffic served (0 if the controller is absent/fully-down); but a running controller exposing a known control-plane RCE (e.g. CVE-2025-1974) is a security finding regardless of route count** (see §1.4). |
| Scale / Volume | 10 | **Count of routes that actually need work** = total routes − 0-effort routes. Do NOT scale off the raw total. (Ingress Discovery, Routing Topology) |
| Backend Compatibility | 5 | Exotic backends, `ExternalName`, service-type edge cases (Ingress Resource Analysis) |

Caps deliberately sum to 125 (over-provisioned) so a genuinely high-change estate floors toward 0 — that is intended: much change ⇒ low score.

### 1.4 — Scoring algorithm (deterministic — follow EXACTLY)

```
# Per-finding base points by Impact (reuse the rating you already assigned)
def base_points(impact):
    # 0 (🟢 non-event) and Unknown (⬜) both contribute 0 pts, but MUST still be listed.
    return {5: 10, 4: 6, 3: 4, 2: 2, 1: 1, 0: 0}.get(impact, 0)
# Impact 0 (🟢 non-event) = 0 pts: absent controller, empty/orphaned dead config, or a CVE on a
# controller that is absent/fully-down. NOTE: a running controller with a control-plane CVE
# (e.g. CVE-2025-1974) is NOT a non-event even at zero routes — rate it 1–5 per §1.4.
# A broken controller WITH bound routes is an active outage: flag it separately, OUTSIDE this score.

# Three independent dimensions STACK on the same controller/route (do not let one override another):
#   1. migration-difficulty  -> the config-complexity categories (Feature-Gap / Routing / TLS / ...)
#   2. tech-debt             -> present-but-broken with ZERO bound routes = +1 (Controller Health cap),
#                               ALWAYS paired with the cleanup note. Absent = 0 (never 1). Broken WITH
#                               bound routes = active outage, flagged OUTSIDE this score (not +1, not 0).
#   3. security (CVE/EOL)    -> data-plane severity scales with LIVE traffic (0 if absent/fully-down);
#                               a control-plane RCE (e.g. CVE-2025-1974) counts even at zero routes.
# Effort to remediate is NOT a dimension — never raise/lower points by how hard the fix is.

# Tier-B feature impact (CORS / IP-allowlist / rate-limit):
#   Impact 2 if performance/hardening only (not in the business-logic path)
#   Impact 3 if entangled with business-logic flow (multiple workstreams)
# NEVER score a Tier-B feature above Impact 3.

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
gate += 1 if controller is EOL with an active exploitable CVE and no maintenance window, OR a running controller exposes a control-plane RCE (e.g. CVE-2025-1974, admission webhook) at ANY route count — zero routes included (this is a non-route condition, counted as a condition not a route)
gate += 1 if EKS Auto Mode managed LB and a self-managed AWS LB Controller race for ownership
# gate == 0  -> "✓ No re-architecture blockers"
# gate  > 0  -> "⛔ N route(s)/condition(s) need redesign or approval"
```

### 1.5 — Score interpretation

| Score | Label | Meaning |
|-------|-------|---------|
| 90–100 | **TRIVIAL** | Mechanical — ALB Controller / ATX auto-converts; hours |
| 80–89 | **EASY** | Minor manual tweaks |
| 70–79 | **MODERATE** | Several features need manual mapping; plan it |
| 60–69 | **HARD** | Significant feature gaps or risky cutover |
| 0–59 | **VERY HARD** | Large amount of change across the estate |

The **Re-architecture Gate** is reported independently of the band: e.g. *"82 / EASY · ⛔ 1 route needs redesign"* is valid — the estate is mostly trivial, but one route still needs a rethink. Score answers "how much work?"; the gate answers "does anything need a redesign decision?".

> **When the gate fires on a security condition, name it in the bottom line.** A zero-route control-plane CVE (e.g. CVE-2025-1974) caps at Impact 5 = 10 pts, so the score can land at **90 / TRIVIAL** — genuinely little *migration* work, because there is nothing to migrate. That band must **never** be read as "safe": whenever the gate carries an **EOL/CVE control-plane** condition, the one-line bottom-line **MUST** name it explicitly and mark it urgent — e.g. *"90 / TRIVIAL · ⛔ CVE-2025-1974 (control-plane RCE) — nothing to migrate, but patch or replace the vulnerable controller urgently."* The score keeps measuring migration work; the red gate carries the security severity.

### 1.6 — Build the Score Breakdown table (MANDATORY)

Before writing the headline, produce this table so the math is auditable. Sum `base_points` per category, apply the cap, order highest-deduction first. The **Total** must equal `100 − score`. A **present-but-broken controller with zero bound routes** appears as a **tech-debt row (1 pt)** under Controller Health; a **broken controller with bound routes** is an **active outage** — surface it as an urgent flag next to the score, **not** as a scored row. **Non-events (absent controller, empty/orphaned dead config, CVE on an absent/fully-down controller) MUST be listed at 0 pts** so the reader sees they were considered and deliberately not counted. Add a final **Re-architecture Gate** line stating the count and which routes (it does not change the total).

```
| Category | Findings (impact) | Raw pts | Capped | Cap |
|----------|-------------------|---------|--------|-----|
| Feature-Gap — No Equivalent (Tier A) | snippet on /checkout (5) | 10 | 10 | 30 |
| Feature-Gap — Workaround Exists (Tier B) | CORS (2), rate-limit (2), allowlist (2) | 6 | 6 | 10 |
| Controller Health & EOL/CVE | broken **traefik** pod, zero bound routes — tech debt (1) | 1 | 1 | 10 |
| ... | ... | ... | ... | ... |
| Non-events (0 pts, listed for transparency) | absent 2nd controller; 12 orphaned **nginx** Ingress objects (no nginx controller installed); CVE on the fully-down traefik pod | 0 | 0 | — |
| **Total deductions** | | | **-XX** | |
| **Re-architecture Gate** | 1 route — snippet on /checkout | — | — | — |
```

> **Note on the sample:** the classes are intentionally **distinct** — the broken controller is `traefik` (so it genuinely has *zero* bound routes) while the 12 orphans are `nginx` (no nginx controller present). If the orphans shared the broken controller's class they would be **bound** to it — that is a **suspected active outage**, not a zero-bound tech-debt row; never mix those two states on one class.

Then: `Score = 100 − (total capped deductions) = XX — [LABEL]`, plus the gate badge.

### 1.7 — Worked example (reflecting the feedback)

Estate: **18 ingresses** — **6 already on ALB** (0 effort, done) and **12 needing work** (per §1.3: routes needing work = total − 0-effort = 18 − 6 = **12**). The 12 are **2 plain class-switch moves** + **10 with feature complexity**. A bare nginx→alb class switch is **at least Medium** (it provisions a new ALB and only takes traffic after a DNS cutover — see `alb-migration.md`), so the 2 annotation-only moves are **not** free: they count in Scale/Volume and share the estate's single new-ALB cutover — they simply add no *feature-gap* complexity of their own. Of the 10: `configuration-snippet` Lua on `/checkout` (Tier A, no workaround), CORS + rate-limit + IP-allowlist (Tier B, performance-only → Impact 2), `rewrite-target` on 3 routes (Routing, Impact 2 each = annotation-grade), cert-manager→ACM (TLS, Impact 3), NGINX 1.9.x EOL no active CVE (Controller, Impact 3).

```
Feature-Gap Tier A:  10  (cap 30)   # /checkout snippet  -> also Gate +1
Feature-Gap Tier B:   6  (cap 10)   # CORS+rate-limit+allowlist, Impact 2 each
Routing:              6  (cap 20)   # 3 rewrites @ Impact 2 (the 2 class-switch moves add no routing complexity; counted only in Scale/Volume below, never as a separate row)
TLS:                  4  (cap 15)   # cert-manager -> ACM
Controller:           4  (cap 10)   # nginx EOL, no CVE
Scale/Volume:         4  (cap 10)   # 12 routes need work (NOT 18) -> Impact 3
Σ = 34  ->  score = 100 − 34 = 66  (HARD)

Re-architecture Gate = 1  ->  "⛔ 1 route needs redesign (snippet on /checkout)"
```

Final: **66 / HARD · ⛔ 1 route needs redesign.** Contrast with v1, which floored the same cluster at **13 / VERY HARD** by maxing Feature-Gap on soft items and then locking the ceiling. The new model credits the 6 done routes, counts **12** (not 18) for volume, drops CORS/allowlist/rate-limit to Impact 2, treats the 2 class-switch moves as real (Medium) work rather than zero, and reports the one true blocker as a gate instead of erasing the number.

## Step 2: Consistency Checks (MANDATORY)

| Check | Fix |
|-------|-----|
| High-impact (5) item missing from Blockers table | Add it |
| Medium-impact item missing from Recommendations table | Add it |
| Executive Summary mentions wrong rating | Fix to match master list |
| Prose paragraph that should be a table | Convert to table |
| Raw YAML in findings (not Migration Approach) | Replace with summary |
| Score Breakdown total ≠ (100 − score) | Recompute — the table is the source of truth |
| CORS / IP-allowlist / rate-limit scored above Impact 3 | Re-rate: Impact 2 (perf/hardening) or 3 (business-logic-entangled) |
| Routes already on ALB / Gateway API counted as work | Set to 0 effort; exclude from Scale/Volume count |
| Scale/Volume scored off the raw total, not routes-needing-work | Recount excluding 0-effort routes |
| Re-architecture Gate count ≠ (Tier-A/passthrough/ownership **route** findings **plus non-route conditions**: no-rollback cutover, EOL/CVE control-plane exposure, Auto Mode LB ownership race) | Reconcile the gate to the master list **including the condition triggers** — a security/CVE condition legitimately raises the gate with **zero** route findings; do not delete it, and render it as `⛔ … condition(s)`, not a phantom route |
| Headline `[[SCORE:nn:LABEL]]` band ≠ the §1.5 table | Fix the label to match the number |

## Step 3: Write Topology JSON

Save to `~/ingress_migration/<cluster>/topology.json`. Include nodes (EC2 instances).

## Step 4: Write Markdown Report

**Filename:** `~/ingress_migration/<cluster>/report.md`

### Content Rules (MANDATORY)

1. **Use tables for all structured data.** Never write lists of facts as prose.
2. **No ID column in any table.** Remove all "ID" columns — they add no value for the reader.
3. **No raw YAML/config in findings.** YAML belongs only in Migration Approach.
4. **Every finding cell: max 2 sentences.**
5. **No filler text.** Go straight to content.
6. **One Migration Difficulty Score (0–100), derived only from the rated findings.** It is a deterministic roll-up of the per-finding Impact ratings (see Step 1), shown once on the Overview page — not a separate prescriptive verdict. The migration-path decision still belongs to the team. Do NOT invent ad-hoc per-section sub-scores.
7. **No ASCII art diagrams.** The HTML has the 3D routing diagram.
8. **Multi-value cells in tables:** put each item on its own line using `<br>` (the renderer turns this into real line breaks). For **Current Configuration**, use nested bullet/sub-bullet lists instead of a table.
9. **Executive Summary = one-shot understanding for a non-technical reader.** Top-level bullet per impact theme, indented sub-bullets for specifics. Bold the key term in each bullet; wrap the most damaging facts in `!! !!` (renders red).
10. **Emphasis syntax (supported by the renderer):** `**bold**` for key terms, `!!red highlight!!` for high-impact / at-risk items, backticks for `versions/code`. Use sparingly — only words that carry the impact.
11. **Lead with impact.** Order Executive Summary bullets and Assessment Summary rows from highest impact to lowest.
12. **Download buttons (renderer tokens):** drop `[[DL:gateway-api]]`, `[[DL:alb]]`, `[[DL:atx]]`, or `[[DL:current]]` anywhere in the markdown — the renderer replaces each with a one-click download button for that option's combined routing config (built from the exported manifests). Prefer a download button over printing long target/current config text.
13. **In-page anchor links:** write `[blocker](#blockers)` to link to a section — the renderer auto-scopes the anchor to the cluster (e.g. `#c0-blockers`). Use this wherever the text says "see Blockers".
14. **Impact everywhere, by the rubric:** Assessment Summary, Ingress Discovery, Routing Topology, Traffic & Routing, Blockers, Recommendations, Ingress Resource Analysis, DNS & Certificates Analysis, Migration Risk all use the **Impact 0–5** scale (🟢0 / 🟡1-2 / 🟠3-4 / 🔴5) — never GREEN/AMBER/RED. Every score MUST be justified against the **Impact Indicator** rubric (priority order: business/revenue · security/reputation · effort — and effort never sets severity), not ad-hoc judgement. Note: easy-to-deploy prerequisites (e.g. installing CRDs) are LOW even if they block a path.

### Report Template (follow EXACTLY)

```markdown
# EKS Ingress Migration Assessment Report

| Information | Value |
|-------------|-------|
| Cluster | [name] |
| Region | [region] |
| Kubernetes Version | [version] |
| Account ID | [account-id] |
| Assessment Date | [YYYY-MM-DD HH:MM] |

---

## Migration Difficulty Score

> Place this as the first authored section on the Overview page (the renderer injects the 3D Routing Diagram just above it, so the rendered flow is: cluster info → 3D diagram → this score → Executive Summary). The headline is the `[[SCORE:nn:LABEL]]` token (colored gauge, green = easy / red = hard) optionally followed by a `[[GATE:n]]` token (re-architecture badge: green ✓ when `n` is 0, red ⛔ when `n` > 0). `nn` is the 0–100 number from Step 1; `LABEL` is the band. One sentence states the bottom line, then the Score Breakdown table makes the math auditable.

[[SCORE:66:HARD]] [[GATE:1]]

[One sentence: how much change leaving NGINX needs for this cluster and the single biggest driver. State how many routes are already done (0 effort) and how many actually need work. If the gate is > 0, name the route(s) that need redesign.]

### Score Breakdown

| Category | Findings (impact) | Deduction | Cap |
|----------|-------------------|-----------|-----|
| [highest-deduction category] | [finding (impact), …] | -X pts | [cap] |
| [next] | [...] | -X pts | [cap] |
| **Total deductions** | | **-X pts** | **Score: XX% — [LABEL]** |
| **Re-architecture Gate** | [N route(s)/condition(s) + which, or "none"] | — | informational |

> The gate row never changes the total — it flags routes that need a redesign/approval decision. Routes already on ALB / Gateway API / a supported 3rd-party controller are listed at **0 pts** and excluded from the Scale/Volume count.

---

## Executive Summary

> Write for a non-technical / low-tech reader — one glance must answer "how risky is this and why." Lead with the biggest impact. **Bold** the key noun in each bullet; wrap the most damaging facts in `!! !!` so they render red. Split any bullet that lists multiple items into indented sub-bullets.

- **Ingress controllers:** [N] in use — !![the single biggest risk, e.g. one is End-of-Life with known CVEs]!!
  - [Controller A] `vX` (modern)
  - [Controller B] `vX` (modern)
  - [Controller C] `vX` !!(EOL / unsupported)!!
- **Biggest migration blocker:** !![the one thing most preventing a clean migration]!! — [one phrase why]
- **Conversion effort:** [N] Ingress resources — [X] convert cleanly, !![Y] need redesign!! ([features with no Gateway API equivalent])
- **Scope:** [namespaces] namespaces, [hosts] hosts, TLS [partial — X of Y]

---

## Impact Indicator

> Place this rubric **before Assessment Summary** (Overview group). EVERY Impact score in the report MUST follow it — do not invent ad-hoc severities. Impact is set by **priority order: (1) business logic / revenue — the live traffic at stake · (2) security / reputation · (3) effort to remediate**. Priority order applies **within a single finding** — it ranks which dimension sets that finding's Impact and breaks ties. It does **not** override presence, and it does **not** zero out a real security exposure just because the business traffic behind it is small: **security anchors on exposure / blast-radius, business on live traffic.** Where the *same object* carries migration-difficulty **and** tech-debt **and** security concerns, those **stack** as separate Score Breakdown rows (see `ingress-discovery.md`). **Effort is NOT a severity driver** — never raise or lower Impact because a fix looks easy or hard (that depends on who does it). Render as a table, one row per band, each cell a bullet list.
>
> **Presence is decided by estate state — not by a "serves no live traffic" test:** an **absent** controller / **empty estate** / **orphaned dead config** is a **non-event (0)** — nothing to migrate. A **present-but-broken** controller with **zero bound routes** is **tech debt (+1)** with a cleanup note; **with bound routes** it is a **suspected active outage**, flagged urgently **outside** the 0–100 score. **Carve-out:** a running controller with a **control-plane CVE** (e.g. an admission-webhook RCE) is a security finding **even at zero routes**. Only **live** traffic anchors the *business* dimension; *security* is anchored by exposure.
>
> **Execution risk counts — do NOT score by YAML-edit size.** A small manifest change can still be high-impact. Specifically: changing `ingressClassName` to a *different controller* (e.g. nginx→alb) **provisions a brand-new load balancer** and only takes traffic after a **DNS cutover** (it is a parallel-run + cutover, not a no-op edit); moving a feature that has **no faithful equivalent** (CORS, rate-limit, external auth) to WAF/app usually needs **application/code changes**; and any TLS/cert-store change done together with routing changes risks **SSL handshake errors / downtime**. Score these by the operational risk, not the diff size.

| Impact | Meaning |
|--------|---------|
| 🟢 0 Non-event | - **Business:** serves no live traffic — nothing at stake<br>- **Security:** no reachable attack surface (controller absent or fully down)<br>- Absent controller, empty estate, or orphaned/dead config. **List it (with any note) but deduct 0.**<br>- *NOT a non-event:* a reachable known-CVE/EOL controller (control-plane exposure survives zero routes), or a broken controller **with** bound routes (active outage — flag separately, outside the score). |
| 🟡 1–2 Low | - **Business (primary):** no revenue loss / downtime / lost transactions<br>- **Security:** hardening gap, no business-effective breach (e.g. a secret kept in-cluster, not in a secrets manager)<br>- **Nature:** optional "should/may-do" best practice; **or a present-but-broken controller with zero bound routes = tech debt (1) + cleanup note**<br>- *Effort (note only, not scored):* typically hours–1 day, single-scope |
| 🟠 3–4 Medium | - **Business (primary):** revenue loss limited to short downtime, or a moderately-important live flow affected<br>- **Security:** breach with limited reputation / trust loss (weigh likelihood & history)<br>- **Nature:** tech debt / weak design, hard to reverse, costly to fix later<br>- *Effort (note only, not scored):* usually area / single-cluster scope |
| 🔴 5 High | - **Business (primary):** significant revenue loss or prolonged downtime on business-critical / public live traffic<br>- **Security:** breach with major loss or reputational damage on a live path (weigh likelihood & history)<br>- **Nature:** needs re-design / re-architecture, maybe business or provider approval<br>- *Effort is NOT a factor — do not downgrade a business-critical finding just because the edit looks small, and do not upgrade a trivial one just because it looks laborious.* |

---

## Assessment Summary

> Rate each theme by **migration Impact 0–5**, highest first. Impact = how much **live traffic / security is at stake** if that feature cannot transfer cleanly to the target versus the current NGINX/Ingress setup — **not** the remediation effort (effort depends on who implements it and never sets severity).
> Do **NOT** rate trivial "is X installed" prerequisites the customer already knows (e.g. "Gateway API CRDs not installed") — rate the **feature transfer/replacement risk** instead.
> Color bands: **0 = 🟢 non-event**, **1–2 = 🟡 low**, **3–4 = 🟠 medium**, **5 = 🔴 high**.

| Theme | Impact | Why — live traffic / security at stake vs. current setup |
|-------|--------|----------------------------------------------------------------|
| [highest-impact theme] | 🔴 5 | [which feature can't transfer cleanly + what live traffic / security is at stake] |
| [next] | 🟠 4 | [...] |
| [next] | 🟠 3 | [...] |
| [next] | 🟡 2 | [...] |
| [lowest] | 🟡 1 | [...] |

> Rows are themes framed as "what's at stake if it can't transfer cleanly", e.g.: NGINX snippet/auth/mirror features → no Gateway API equivalent; controller currency (EOL vs modern); TLS/cert model (K8s Secret vs ACM); routing complexity (regex/rewrite); canary/traffic-split portability. Order strictly by Impact descending.

---

## Current Configuration

## Current Configuration

> Goal: convey the environment at a glance. Use a bullet list. For any value with multiple items (controllers, namespaces), use indented **sub-bullets** — never a comma list or a raw `<br>`.

- **Ingress controllers:**
  - [controller-a] `vX` (modern)
  - [controller-b] `vX` (modern)
  - [controller-c] `vX` !!(EOL)!!
- **Controller namespaces:**
  - [ns1]
  - [ns2]
- **Total Ingress resources:** [count]
- **Namespaces with Ingress:**
  - [ns1]
  - [ns2]
- **Routing pattern:** [host-based / path-based / both]
- **TLS enabled:** [partial — X of Y]
- **Load balancer types:** [ALB / NLB / ClusterIP]
- **Nodes:** [count] — [instance types]

---

## Ingress Discovery

| Item | Impact | Current State | Recommendation |
|------|--------|---------------|----------------|
| Ingress Controllers Installed | [🟢0 / 🟡1-2 / 🟠3-4 / 🔴5] | [summary] | [action or "None required"] |
| IngressClass Resources | [impact] | [summary] | [action or "None required"] |
| Ingress Resource Inventory | [impact] | [summary] | [action or "None required"] |

---

## Routing Topology

> Keep this table narrow so it fits. Combine host+path into one **Route** column, backend+port into **Backend:Port**, TLS as ✓/—, and add a per-route **Impact** (0–5). Omit a shared host suffix (note it above the table). Use `<br>` for multi-backend cells.

| Ingress | NS | Controller | Route (host · path) | Backend:Port | TLS | Impact |
|---------|----|------------|---------------------|--------------|-----|--------|
| [name] | [ns] | [controller] | [host · path] | [svc:port] | [✓/—] | [impact] |

---

## Traffic & Routing

| Item | Impact | Current Config | Recommendation |
|------|--------|----------------|----------------|
| Routing Pattern Mapping | [impact] | [[DL:current]] | [action] |
| Advanced Traffic Features | [impact] | [[DL:current]] | [action] |
| Cross-Namespace Routing | [impact] | [[DL:current]] | [action] |

> **Current Config column:** use the `[[DL:current]]` download button (the current manifests are already exported) rather than printing long config strings.

---

## Migration Options

> Three migration paths. **Every option uses the same layout** (apply Option 1 as the template):
> 1. an **info panel** (blockquote): `> **What:** … · **Effort:** Low/Medium/High · **Best when:** …` then a second line `> **Routing config:** [[DL:<token>]]`
>
> *(The panel's **Effort** is a **path-level** descriptor — how much work the whole migration path is — and is **not** a per-finding Impact. It never feeds the Score Breakdown; the effort-is-not-severity rule governs finding **Impact**, not this path summary.)*
> 2. aligned **Phase 1 — Foundation / Phase 2 — Convert & Test / Phase 3 — Cutover / Phase 4 — Cleanup**, each a `| Step | Action |` table with numbered steps.
> Do NOT print verbose target config — the `[[DL:*]]` button downloads it. Where a route can't convert, link `(see [blocker](#blockers))`.
> No summary/intro blockquote above the options — send the reader straight into Option 1 so they engage with the steps.

### Option 1: Gateway API

> **What:** Kubernetes-native successor to Ingress (HTTPRoute + Gateway). · **Effort:** Medium · **Best when:** you want the long-term standard.
> **Routing config:** [[DL:gateway-api]]
> **Caveats:** L7 ALB Gateway API support is recent (HTTPRoute ≥ v2.14, GA 2026 line) — verify TLS handling and routing filters per route before cutover. On **EKS Auto Mode** running a self-managed LBC too, scope `GatewayClass`/`IngressClass` per controller to avoid !!load-balancer ownership conflicts!!.

#### Phase 1 — Foundation
| Step | Action |
|------|--------|
| 1 | Install Gateway API CRDs |
| 2 | Verify/upgrade AWS LB Controller (**≥ v2.14** for L7 Gateway API; not needed on Auto Mode) |
| 3 | Create GatewayClass |
| 4 | Create Gateway per listener group |

#### Phase 2 — Convert & Test
| Step | Action |
|------|--------|
| 1 | Generate HTTPRoutes from current Ingress (download config above) |
| 2 | Apply low-risk routes first; validate routing, TLS, health |
| 3 | Routes with no equivalent (snippets/auth/mirror) — redesign (see [blocker](#blockers)) |

#### Phase 3 — Cutover
| Step | Action |
|------|--------|
| 1 | Shift DNS to the Gateway ALB (weighted) |
| 2 | Watch 5xx / latency |
| 3 | Confirm all HTTPRoutes `Accepted=True` |

#### Phase 4 — Cleanup
| Step | Action |
|------|--------|
| 1 | Delete migrated Ingress resources |
| 2 | Remove old controllers |
| 3 | Remove unused IngressClasses |

> Options 2 (ALB) and 3 (ATX) follow the identical panel + Phase 1–4 structure, each with its own `[[DL:alb]]` / `[[DL:atx]]` button. Keep the ALB annotation-conversion table and the ATX "What ATX Converts" table as reference sub-sections under their options.

#### Phase 3: Traffic Cutover

| Step | Action | Validation |
|------|--------|-----------|
| 1 | Update DNS to Gateway LB | [how to verify] |
| 2 | Monitor error rates | [what to watch] |
| 3 | Confirm all routes healthy | [check command] |

#### Phase 4: Cleanup

| Step | Action |
|------|--------|
| 1 | Delete old Ingress resources |
| 2 | Remove old controller |
| 3 | Remove unused IngressClass |

---

### Option 2: AWS Load Balancer Controller (ALB Ingress)

Stay on the Ingress API but swap NGINX annotations for ALB annotations. Gets you WAF, Cognito/OIDC, Shield integration without adopting Gateway API.

**When to choose:** Team not ready for Gateway API, needs ALB features immediately, or has many Ingress resources to convert quickly.

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

#### Migration Steps

| Step | Action | Validation |
|------|--------|-----------|
| 1 | Install AWS LB Controller **v2.7.2+** (ALB Ingress); not needed on EKS Auto Mode | `kubectl get deploy -n kube-system aws-load-balancer-controller` |
| 2 | Provision ACM certificates | `aws acm list-certificates` — all ISSUED |
| 3 | Convert annotations per mapping above | `kubectl apply --dry-run=client -f <file>` |
| 4 | Deploy migrated Ingress (new ALB created) | `kubectl get ingress -A` shows ALB address |
| 5 | DNS weighted routing: shift traffic CLB→ALB | `dig <host>` resolves to new ALB |
| 6 | Remove NGINX controller + orphaned TLS Secrets | `kubectl delete deploy -n ingress-nginx ingress-nginx-controller` |

#### Per-Ingress Conversion Table

| Ingress | Namespace | Key Changes | Complexity |
|---------|-----------|-------------|-----------|
| [name] | [ns] | [e.g., "rewrite→transforms, TLS→ACM"] | [Low/Medium/High] |

> **Manifests exported to:** `<cluster>-manifests/target/alb/`

---

### Option 3: AWS Transform (ATX) — Automated

For customers with AWS Transform access — fully automated manifest rewriting. ATX reads the included Transform Definition and converts all NGINX Ingress manifests to ALB annotations automatically.

**When to choose:** Many Ingress resources (>10), want consistent automated output, have ATX workspace access.

#### How It Works

| Step | Action | Who |
|------|--------|-----|
| 1 | Upload TD from `references/atx/td_ingress-nginx-lbc/transformation_definition.md` | You |
| 2 | Point ATX at your Ingress manifest repository | You |
| 3 | ATX scans, converts, validates automatically | ATX |
| 4 | Review diff and merge | You |
| 5 | Deploy + DNS cutover | You |

#### What ATX Converts

| Pattern | Before (NGINX) | After (ALB) |
|---------|----------------|-------------|
| IngressClass | `nginx` | `alb` |
| URI Rewrite | `rewrite-target` + regex | `transforms.<svc>` JSON |
| TLS | K8s Secrets | ACM `certificate-arn` |
| Auth | `auth-url` | `auth-type: oidc` |
| CORS | `enable-cors` | Removed (WAF/app) |
| Internal | `whitelist-source-range` | `scheme: internal` |

#### ATX Validation (Automatic)

- ✅ No `ingressClassName: nginx` remains
- ✅ No `nginx.ingress.kubernetes.io/*` annotations
- ✅ All rewrites use valid `transforms.<svc>` JSON
- ✅ All TLS ingresses have ACM + ssl-redirect + ssl-policy
- ✅ `kubectl apply --dry-run=client` passes

> **TD location:** `references/atx/td_ingress-nginx-lbc/transformation_definition.md`
> **Contact:** AWS account team for ATX workspace onboarding

---

## Blockers

> Lives under **Migration Approach** (not Analysis). Finding name only — no "— RED" suffix. **Impact 0–5** (🟢0 / 🟡1-2 / 🟠3-4 / 🔴5). **Action Required** is a bullet list — use `- item<br>  - sub-item` for sub-bullets. No Effort column (manday effort depends on team experience and can't be fixed reliably).

| Finding | Impact | Action Required |
|---------|--------|-----------------|
| [finding name] | [🔴 5] | - [action]<br>  - [sub-action] |

> If no high-impact items exist, write: "No blockers identified."

---

## Recommendations

> Lives under **Migration Approach**. **Impact 0–5** = how disruptive *implementing* the action is to the running app / production (🟢0 / 🟡1-2 / 🟠3-4 / 🔴5). No Effort column.

| Finding | Action | Priority | Impact |
|---------|--------|----------|--------|
| [finding name] | [specific action] | [High/Medium/Low] | [🟡/🟠/🔴 n] |

---

## Ingress Resource Analysis

> **Impact 0–5** = severity *if left as-is* (not migrated). Usually low/medium — the app keeps running on NGINX today (🟢0 / 🟡1-2 / 🟠3-4 / 🔴5). **Recommendation** is a bullet list (`- item<br>  - sub-item`). No Reference column.

| Item | Impact | Current State | Recommendation |
|------|--------|---------------|----------------|
| Annotation Inventory & Mapping | [impact] | [summary] | - [action]<br>  - [sub-action] |
| TLS Configuration | [impact] | [summary] | - [action] |
| Backend Service Compatibility | [impact] | [summary] | - [action] |

---

## DNS & Certificates Analysis

> Same approach as Ingress Resource Analysis: **Impact 0–5** if left as-is (usually low — DNS/TLS still serve today), bullet **Recommendation**.

| Item | Impact | Current State | Recommendation |
|------|--------|---------------|----------------|
| external-dns Gateway API Support | [impact] | [summary] | - [action] |
| cert-manager Gateway Integration | [impact] | [summary] | - [action] |
| ACM Integration | [impact] | [summary] | - [action] |

---

## Migration Risk

| Item | Impact | Current State | Recommendation |
|------|--------|---------------|----------------|
| Downtime Risk | [impact] | [summary] | - [action] |
| Feature Gap Analysis | [impact] | [summary] | - [action] |
| Rollback Readiness | [impact] | [summary] | - [action] |

---

## AWS Reference Links

| Topic | URL |
|-------|-----|
| Gateway API on EKS | https://docs.aws.amazon.com/eks/latest/userguide/gateway-api.html |
| AWS Load Balancer Controller | https://kubernetes-sigs.github.io/aws-load-balancer-controller/ |
| Gateway API Specification | https://gateway-api.sigs.k8s.io/ |
| HTTPRoute API Reference | https://gateway-api.sigs.k8s.io/api-types/httproute/ |
| Gateway API Migration Guide | https://gateway-api.sigs.k8s.io/guides/migrating-from-ingress/ |
| external-dns Gateway API | https://kubernetes-sigs.github.io/external-dns/latest/sources/gateway-api/ |
| cert-manager Gateway API | https://cert-manager.io/docs/usage/gateway/ |
| EKS Best Practices | https://docs.aws.amazon.com/eks/latest/best-practices/ |
| EKS User Guide | https://docs.aws.amazon.com/eks/latest/userguide/ |
```

Do NOT fabricate URLs beyond this list.

**Section placement in nav:**
- **Overview:** Information table, **3D Routing Diagram** (injected by the renderer), **Migration Difficulty Score** (headline gauge + Score Breakdown), Executive Summary, Impact Indicator (rubric, just before Assessment Summary)
- **Assessment Summary:** Assessment Summary table, Current Configuration, Ingress Discovery
- **Routing Topology:** Routing Topology table, Traffic & Routing
- **Migration Approach:** Migration Options (Option 1: Gateway API, Option 2: ALB Controller, Option 3: ATX — same panel + Phase 1–4 layout), **Blockers**, **Recommendations**
- **Analysis:** Ingress Resource Analysis, DNS & Certificates Analysis, Migration Risk
- **References:** **Export Materials** (the generated manifests + download buttons, rendered by the tool), then **AWS Reference Links**

Note: There is **no Migration Planning section** (scope/complexity/timeline fold into Migration Options and Blockers) and **no Investigate Manually section**. Blockers/Recommendations live under **Migration Approach**. The former "Appendix" is **Analysis**. **Export Materials** and **AWS Reference Links** live under **References** (Export Materials first). Gateway API Readiness is folded into Migration Options, not a standalone section.

## Step 5: Generate HTML Report

After ALL cluster markdown reports are written, generate a **single combined HTML**:

```bash
# Single cluster
python3 tools/report_to_html.py \
  ~/ingress_migration/<cluster>/report.md \
  --topology ~/ingress_migration/<cluster>/topology.json \
  --manifests ~/ingress_migration/<cluster>/manifests

# Multiple clusters — one HTML with cluster dropdown
python3 tools/report_to_html.py \
  ~/ingress_migration/cluster-a/report.md ~/ingress_migration/cluster-b/report.md \
  --topology ~/ingress_migration/cluster-a/topology.json ~/ingress_migration/cluster-b/topology.json \
  --manifests ~/ingress_migration/cluster-a/manifests ~/ingress_migration/cluster-b/manifests \
  -o ~/ingress_migration/EKS-Ingress-Migration-<YYYY-MM-DD>-<HHMM>.html
```

Do NOT generate HTML manually. Always use the script.

## Step 6: Export Materials

> **Directory contract (required by `report_to_html.py`):** lay manifests out as `current/`, `target/gateway-api/`, and `target/alb/` under the cluster's `manifests/` dir. The renderer recursively loads these subtrees (`rglob`) and powers the `[[DL:current]]` / `[[DL:gateway-api]]` / `[[DL:alb]]` download buttons — a flat `target/*.yaml` layout will not be found.

After generating the HTML report, export manifest files for each cluster:

**Output directory:** `~/ingress_migration/<cluster>/manifests/`

```
~/ingress_migration/
├── <cluster>/
│   ├── report.md                              # Cluster markdown report
│   ├── topology.json                          # Topology data for 3D view
│   └── manifests/
│       ├── current/                           # Existing Ingress resources (clean YAML)
│       │   └── <namespace>-<ingress-name>.yaml
│       └── target/
│           ├── gateway-api/                   # Gateway API resources (apply order)
│           │   ├── 00-gateway-api-crds.yaml
│           │   ├── 01-gatewayclass.yaml
│           │   ├── 02-gateway.yaml
│           │   ├── 03-httproute-<name>.yaml
│           │   └── 04-referencegrant-<name>.yaml  # Only if cross-namespace
│           └── alb/                           # ALB Controller Ingress (converted)
│               └── <namespace>-<ingress-name>.yaml
├── EKS-Ingress-Migration-<YYYY-MM-DD>-<HHMM>.html  # Combined HTML (all clusters)
└── ...
```

**Rules:**
1. `current/` — Extract each Ingress resource as YAML. Strip `status`, `managedFields`, `resourceVersion`, `uid`, `creationTimestamp`, `generation`. Keep only `apiVersion`, `kind`, `metadata.name`, `metadata.namespace`, `metadata.annotations`, `metadata.labels`, `spec`.
2. `target/gateway-api/` — Generate Gateway API manifests based on assessment findings. Number-prefix for apply order. Include comments explaining what each resource does.
3. `target/alb/` — Generate ALB Controller Ingress manifests by applying the annotation mapping from `references/alb-migration.md`. Each file mirrors the original Ingress but with ALB annotations.
4. The `00-gateway-api-crds.yaml` file should contain only a comment with the install command — not the actual CRD content.
5. All manifests must be valid YAML that can be applied with `kubectl apply -f`.
6. **Snippet / blind-spot safety (CRITICAL):** if any source Ingress uses `configuration-snippet`/`server-snippet`/`modsecurity-snippet` (or §5.5 found snippet-injected routes), the generated target manifests are **incomplete** — they cannot represent snippet-injected `location`s (e.g. `/healthz`, deny `/internal/`). For every such Ingress you MUST:
   - **Not** generate a silently-apply-ready target; instead emit a placeholder containing a prominent header comment `# INCOMPLETE — snippet-injected routes not represented; hand-port before applying` listing the missing paths/behaviours.
   - Replace rule 7's wording for affected files with **"review & hand-port — DO NOT blind-apply"**. Blind-applying would drop health-check paths and access-control denies, breaking probes and exposing internal paths.
7. Inform the user: "Manifests exported to `~/ingress_migration/<cluster>/manifests/`. Files for snippet-free ingresses are apply-ready (`kubectl apply -f …`); files flagged **INCOMPLETE** require manual hand-porting of snippet-injected routes first."
8. **Controller-ownership pre-apply gate (CRITICAL on EKS Auto Mode):** if the cluster runs **both** EKS Auto Mode's built-in load balancing **and** a self-managed AWS LB Controller, the exported manifests MUST carry a blocking warning: *"Do NOT apply until controller ownership is reconciled."* Two reconcilers will **race** for the same AWS resources (port/target-group/IP binding locks, duplicate work, broken networking). The user must first choose **one** owner — either (a) remove the self-managed LBC and use Auto Mode managed load balancing, or (b) disable Auto Mode's load-balancing capability and let the Helm-installed LBC own everything — and scope `IngressClass`/`GatewayClass` accordingly. State this as a prerequisite step, not a footnote.

**Pass manifests directory to HTML report tool** via `--manifests` flag so the HTML can offer a download button.
