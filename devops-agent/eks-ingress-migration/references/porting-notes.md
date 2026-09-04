# Porting Notes — eks-ingress-migration

This file documents the differences between the Claude Code version (`skills/eks-ingress-migration/`) and this DevOps Agent port. It is for maintainers, not for the agent to read during execution. **Exclude it from the uploaded skill zip** (`zip -r ../eks-ingress-migration-skill.zip . -x './references/porting-notes.md'`) — it ships in the repository for maintainers only.

> **Staleness check:** the tables below describe the upstream skill at a point in time and can drift as `skills/eks-ingress-migration/` evolves. Re-verify each row against upstream when materially changing either copy, and update the date here. Last verified: 2026-08-30, against upstream `main` (post-#129/#153/#154).

## Differences from the Claude Code version

| Aspect | Claude Code (`skills/eks-ingress-migration/`) | DevOps Agent (this skill) |
|--------|-----------------------------------------------|---------------------------|
| Execution model | Interactive — asks "assess all clusters, or select specific ones?" on ambiguity | Fully autonomous — Step 0 hard-stop decision table, no interactive prompts |
| Cluster selection | Discovers all clusters across regions, assesses many per run | Discovers across regions, assesses **one** cluster per run; **HARD STOP** when more than one is found and none was named (never auto-selects, never assesses all) |
| Tool access | `aws` CLI, `kubectl`, EKS MCP server | AWS control-plane APIs (read-only) + Kubernetes API via the Agent Space EKS access entry (read-only). No Bash, no kubectl, no MCP. |
| Kubernetes reads | `kubectl get/describe`, or MCP `list_k8s_resources` | Expressed as "**Via Kubernetes API**" capability descriptions, not `kubectl` pipelines |
| Report output | Markdown file written to `~/ingress_migration/<cluster>/report.md` | Markdown rendered **inline in the response**; no files written, no output path reported |
| HTML report | `tools/report_to_html.py` renders an interactive dashboard with a 3D routing diagram, score gauge, gate badge, cluster dropdown, and per-option download buttons | **Omitted** — no script execution. Report generation is expressed as instructions + the markdown template; the tool's deterministic renders became literal text (see "Renderer tokens" below). |
| Topology JSON | Written to `~/ingress_migration/<cluster>/topology.json`, consumed by the 3D view | Emitted as one fenced `json` block in the report's References section; same schema, same controller-naming contract, now joined against the Routing Topology table instead of a 3D renderer |
| Manifest export | YAML files written under `<cluster>-manifests/current/` and `target/` | Same content rendered inline as labelled fenced `yaml` blocks, with a **volume guard** (all routes at ≤ 10; above that, shared target resources + the 10 highest-Impact routes + a table of the deferred remainder, counts stated) |
| Snippet route enumeration | `kubectl exec <nginx-pod> -- nginx -T` as an optional deep read | **Not reachable** — no pod exec. The snippet blind spot becomes a permanent, mandatory caveat and the routing inventory is marked Unverified (see below). |
| Directory naming | `references/samples/`, `references/atx/` nested under `references/` | `assets/samples/`, `assets/atx/` — matches the port convention (`references/` stays flat; data files live in `assets/`) |
| Prerequisites | AWS credentials, Python 3.10+, EKS MCP server, AWS CLI | `references/iam-policy.json` for the Agent Space role + an EKS access entry; no Python, no CLI, no MCP |
| `allowed-tools` frontmatter | Not present upstream either | Not present (prohibited in this runtime) |

## Renderer tokens → literal text

`report_to_html.py` substituted four token families that plain markdown would show literally. Each became text carrying the same information:

| Upstream token | Port replacement |
|---|---|
| `[[SCORE:nn:LABEL]]` (colored gauge) | `**Migration Difficulty Score: <nn> / 100 — <LABEL>**` |
| `[[GATE:n]]` (badge) | The tool's own strings, verbatim: `✓ No re-architecture blockers` (n = 0) / `⛔ <n> blocker(s) need(s) redesign / approval` (n > 0) |
| `[[DL:current]]` / `[[DL:gateway-api]]` / `[[DL:alb]]` / `[[DL:atx]]` (download buttons) | Cross-references to the **Export Materials** section, where the YAML is rendered inline |
| `!!red highlight!!` | `**bold**` |

The `!!…!!` conversion is not cosmetic: `report_to_html.py`'s `inline()` implements `**bold**`, backticks, links and `!!hot!!`, so an unrendered `!!…!!` in a markdown-only runtime would reach the reader as literal exclamation marks. The same applies to the `[[…]]` tokens.

## Capability losses (and how each fails closed)

Every loss below is a **runtime reachability** gap, not a content cut. In each case the port fails closed — it reports reduced confidence rather than a clean negative.

1. **Snippet-injected route enumeration.** Upstream can `exec` into the controller pod and read `nginx -T`. This runtime has no shell, no pod exec, and no in-cluster network path, and `pods/exec` is not granted by the access entry. `traffic-routing.md` §5.5 therefore states that the snippet under-count is permanent and unmeasured, requires the report to say the true route count is **≥** the counted one, and hands both deep reads to the cluster owner as verification steps with the inventory marked Unverified. It never infers "no hidden routes".
2. **Admission-webhook exposure.** `ValidatingWebhookConfiguration` lives in `admissionregistration.k8s.io`, outside the built-in groups an access entry is likely to grant (see the caveat below — the managed policy's rules are unpublished). The #153 tri-state already fails closed, so a `403` lands in **Unverified → treated as exposed** and keeps the 🔴 5 CVE-2025-1974 band. The controller Deployment args (`apps`, which *is* covered) are the primary signal; the VWC read is corroboration.
3. **Gateway API adoption state.** `gateway.networking.k8s.io` and `apiextensions.k8s.io` are CRD groups, which an access-entry policy scoped to built-in groups would not reach. A denied read reports Gateway API as **unconfirmed** and sets `"gatewayApi": { "readStatus": "unconfirmed" }` — never `crdsInstalled: false`, and never a recommendation to install CRDs on the strength of a `403`.
4. **Interactive multi-cluster selection.** Replaced by a hard stop, so the port never silently assesses the wrong cluster.

## Supplementary ClusterRole (optional — closes losses 2 and 3)

The manifest and its rationale live in **`references/supplementary-rbac.md`**, which — unlike this file — **is** included in the shipped skill zip (`setup.sh` excludes only `porting-notes.md`). It is kept there, not here, so the operator-facing instruction is reachable from the packaged skill; do not duplicate the YAML back into this file.

Summary: binding it grants exactly the reads this skill needs, so the webhook tri-state and the Gateway API adoption check resolve definitively instead of degrading. Without it the assessment still completes and simply reports Unverified/unconfirmed. The `AmazonAIOpsAssistantPolicy` sourcing caveat (its rules are unpublished, so coverage is unconfirmable and every read fails closed) is stated there in full.

## Scoring model — carried over unchanged

The Migration Difficulty Score is the part most at risk from a port, so it was copied without modification and re-derived by hand after porting:

- The deduction model (Impact 5→10, 4→6, 3→4, 2→2, 1→1, non-event 0), the per-category caps, `score = max(0, 100 − Σ)`, and the bands (90–100 TRIVIAL · 80–89 EASY · 70–79 MODERATE · 60–69 HARD · 0–59 VERY HARD) are byte-identical to upstream.
- The **#129 learning is present**: an empty/absent estate is **not rated** — no controller + no IngressClass + no Ingress → 100 / TRIVIAL with a "nothing to migrate" note (`report-generation.md` §1.0), including the §1.0-A carve-out that a reachable CVE/EOL controller is still a security finding at zero routes, and the orphaned-Ingress "Migration Crew Alert" path.
- The #153 auth-tier resolution (Basic Auth → OIDC is Tier-B, escalating to Tier-A only with **both** a closed/unmodifiable backend **and** non-interactive callers) and the #154 `lbc-migrate` toolkit path with its assessor/operator fence are carried over intact.
- The §1.7 worked example still totals 10+6+6+4+4+4 = 34 → **66 HARD**, gate 1 — unchanged by the port.

## Mutating commands are documentation, not actions

The skill is assessment-only upstream; here it is also *incapable* of mutation. Operator steps (Gateway API CRD install, LBC feature-gate enable, `lbc-migrate` applies, DNS cutover, `kubectl delete ingress` cleanup) remain in the references as instructions **for the cluster owner to run under their change-management process**. The #154 assessor/operator fence in `lbc-migrate-toolkit.md` is unchanged, and `SKILL.md` Tool Usage Rule 17 states the agent never executes them. Fenced command blocks use plain fences rather than ` ```bash `, matching the other ports, so nothing implies a shell.

## Faithful port vs. faithful defect — and what was corrected

The port is deliberately **minimal-delta**, but "faithful" has two very different meanings and they must not be conflated:

- **Design artifacts** (the scoring model, tier rubric, gate pseudocode, bands, report shape, worked example) — here **identity *is* correctness**. These were copied unchanged and re-derived by hand to prove it; a divergence would be a defect.
- **Factual content** (version floors, annotation names, service capabilities) — here **identity is not correctness**. Copying a wrong version or a non-existent annotation byte-for-byte reproduces the error and ships it to a second audience. Provenance ("it was already like that upstream") is an explanation, never a mitigation.

Review round 1 on #204 found several inherited **factual** defects. Because the port and the published skill would otherwise disagree — or agree on something untrue — they are fixed in **both** copies in this PR, parity-preserving, applying the same rule already used for the navigation-count: **diverge from upstream where the value is plainly wrong, stay identical everywhere else.** Corrected in both `skills/eks-ingress-migration/` and here:

1. **`certificate-discovery` is not a real annotation.** `alb.ingress.kubernetes.io/certificate-discovery: "true"` was shipped as a functional annotation (a sample manifest plus four doc sites). It does not exist in the AWS Load Balancer Controller — absent from the Ingress annotation reference and from the controller's annotation constants (checked v2.7.2 → v3.5.0). Unknown annotations are **silently ignored**, so an operator would believe TLS discovery was active while the listener had no certificate. Certificate discovery is triggered by **omitting `certificate-arn`** with an HTTPS entry in `listen-ports`. The sample now uses the omit pattern.
2. **Gateway API production floor is v3.0.0, not v2.14.** v2.13.3 / v2.14.0 are where L4 / L7 *reconciliation began*; through **v2.15.x** the upstream guide warned *"Using the LBC and Gateway API together is not suggested for production workloads (yet!)"*, and that warning is absent from **v3.0.0** (2026-01-23) onward. The old text let the Option-1 prerequisite gate pass a pre-production controller as production-ready.
3. **`transforms` URI rewrites need LBC v2.15.0.** The install floor was stated as v2.7.2 while 6 of 8 ALB samples use `alb.ingress.kubernetes.io/transforms.<svc>`, introduced in **v2.15.0** (2025-11-14). On v2.7.2 that annotation is silently ignored and **no rewrite happens**. v2.7.2 remains correct for the plain ALB Ingress path; the rewrite path now states v2.15.0.
4. **EKS Auto Mode does not provide Gateway API.** The built-in `eks.amazonaws.com` controller covers **Ingress** and **Service `type: LoadBalancer`** only (Auto Mode load-balancing docs, checked 2026-09-01). A Gateway API target still needs a self-managed LBC at ≥ v3.0.0. The old wording also contradicted `ingress-discovery.md`, which had it right.
5. **Version currency.** Dropped "current" from the v1.5.0 CRD statements (Gateway API's current release is **v1.6.1**) and retargeted the runtime-upgrade recommendation to the current **LBC v3.5.0** line. The CRD pairing is now stated per controller line — **v1.5.0 for v3.4.0**, **v1.6.0 for v3.5.0** — because v3.5.0 is built for Gateway API v1.6.0; the `lbc-migrate` build-tag pin stays at v3.4.0. From Gateway API v1.6.0 TCPRoute/UDPRoute are in the standard channel, so no experimental install is needed for L4.
6. **Tier-A phrasing applied to Tier-B features.** The "Execution risk counts" blockquote called CORS / rate-limit / external auth *"no faithful equivalent"* — the literal Tier-A phrase — while §1.3 classifies them Tier-B *because* a workaround exists. Reworded to "no native ALB annotation" with an explicit pointer that Tier-A requires §1.3's escalation conditions. (Pre-existing, predates #129, disclosed on #153; closed rather than carried again.)
7. **Cosmetic parity.** `ingress-resources.md` `auth-url` row now reads "No **native** equivalent", matching its CORS and affinity siblings, and the upstream `SKILL.md` navigation-count heading now says 6 to match its own 6-row table.

The two `certificate-discovery` occurrences that remain are inside `assets/atx/` — the vendored AWS Transform definition and the AWS blog reproduced beside it. Those are kept **byte-faithful to the artifact ATX actually ships** rather than silently forked, so `atx-guide.md` now carries an explicit caveat that the TD instructs a non-existent annotation and that ATX output must be reviewed for it.

### Still open, deliberately not in this PR

- **Report-template duplication** (a duplicate `## Current Configuration`, doubled Phase 3/4 sub-sections) is carried over from upstream. It reshapes the report template rather than correcting a fact, so it carries different regression risk and belongs in its own change.

