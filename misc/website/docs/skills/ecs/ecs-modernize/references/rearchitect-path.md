---
title: "Module: Rearchitect Path"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-modernize/references/rearchitect-path.md
format: md
---

:::info[Source]
This page is generated from [skills/ecs-modernize/references/rearchitect-path.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-modernize/references/rearchitect-path.md). Edit the source, not this page.
:::

# Module: Rearchitect Path

> **Part of:** [ecs-modernize](../)
> **Purpose:** Turn a Rearchitect strategy outcome into a concrete modernization path — the three ECS compute-model candidates with per-candidate applicability grounded in the analysis findings, the modernization items the detected findings actually require, their effort classification on the three-tier scale this file owns, optional framework-migration paths, and AWS Transform accelerator recommendations — while delegating detailed design to `ecs-architect`
> **Prerequisites:** Scoring and Recommendation ([scoring-and-recommendation.md](scoring-and-recommendation)) — the Rearchitect path is presented from the `scoring`, `recommendation`, `tech_stack`, and `blockers` blocks; it is never assembled without them

This is a **path module**: unlike the orchestrator-neutral analysis modules, ECS-specific vocabulary is expected and deliberate here. Mapping the Rearchitect strategy onto concrete ECS compute models — ECS Express Mode, ECS on Fargate, ECS Managed Instances — happens in this file (and only in the path modules); the scoring module hands over a strategy classification and nothing more.

**Effort-scale definition owner.** The three-tier remediation-effort scale (small / medium / large) is defined in [this file's Effort Scale section](#effort-scale-single-definition) and nowhere else. The both-strategies comparison in [scoring-and-recommendation.md](scoring-and-recommendation) ("Always Present Both Strategies") uses this scale **by reference**; no other file defines a competing scale.

## Table of Contents

- [Inputs](#inputs)
- [Procedure](#procedure)
- [Criteria](#criteria)
  - [Compute-Model Candidates and Applicability](#compute-model-candidates-and-applicability)
  - [Modernization Item Catalog and Mapping Rules](#modernization-item-catalog-and-mapping-rules)
  - [Effort Scale (Single Definition)](#effort-scale-single-definition)
  - [Framework Migration Options](#framework-migration-options)
  - [AWS Transform Applicability Guidance](#aws-transform-applicability-guidance)
  - [Delegation to ecs-architect](#delegation-to-ecs-architect)
- [Output Schema](#output-schema)
- [Edge Cases](#edge-cases)
- [Sources](#sources)

---

## Inputs

- **`tech_stack` block** (required) — languages, frameworks with classification families, runtimes with version and `eol` status, application servers, undetermined items.
- **`blockers` block** (required) — every blocker with category, remediation class (`replatform_ok` / `must_fix`), evidence paths, and reason; or the explicit zero-blocker statement.
- **`scoring` + `recommendation` blocks** (required) — the Fit_Score with its per-dimension breakdown and the strategy classification. The Rearchitect path is presented regardless of which classification came out (both strategies always appear in the report), but its content is grounded in these results.
- **`analysis` envelope** (required) — target identity and partial-analysis state, which propagates into confidence notes.
- **Read-only discipline** — this module runs during the assessment phase: it reads no additional files beyond what Source_Analysis already collected, executes no commands, creates no files, and never starts any code transformation. Its output is held in conversation context for the report module.

Do not run this module before the scoring and recommendation module has produced its outputs (which in turn requires tech stack detection and blocker detection). A Rearchitect path assembled without them has no evidence base.

---

## Procedure

Run the steps in this order:

```
0. Confirm this file has been read in full      -> SKILL.md mandate before executing this module
1. Verify prerequisite outputs are present       -> tech_stack + blockers + scoring + recommendation
2. Present all three compute-model candidates    -> Express Mode, Fargate, Managed Instances —
   with their applicability conditions              always all three, never a subset
3. Judge per-candidate applicability             -> applicable / applicable-after-remediation /
   against the detected stack and blockers          not-applicable, each with grounding findings
4. Derive modernization items from findings      -> catalog mapping rules; no finding -> no item
5. Verify blocker coverage                       -> every blocker requiring remediation under
                                                    Rearchitect maps to >= 1 listed item
6. Classify effort per item                      -> exactly one tier (small / medium / large)
7. Add framework-migration options               -> established paths only, as OPTIONAL items
                                                    with approximate effort
8. Annotate AWS Transform applicability          -> recommendation only; execution belongs to
                                                    the code transformation module post-gate
9. Assemble the output with the delegation note  -> detailed design goes to ecs-architect
```

**Why this order:**

- Candidates before items (steps 2–3 before 4): applicability judgments consume the raw findings; the modernization items then explain *what closes the gap* for candidates marked applicable-after-remediation, so the items must be derived with the candidate gaps already known.
- Coverage verification (step 5) sits between derivation and effort classification: an unmapped blocker discovered late would invalidate the item list, so check completeness before investing in per-item classification.
- Framework migration (step 7) and AWS Transform annotations (step 8) come last among content steps because both attach to already-derived items — they modify presentation (optionality, accelerator notes), never the underlying finding-to-item mapping.

---

## Criteria

### Compute-Model Candidates and Applicability

**Presentation rule (always all three).** Whenever the Rearchitect path is presented, present **all three** compute-model candidates — **ECS Express Mode**, **ECS on Fargate**, and **ECS Managed Instances** — each with its applicability conditions. Never omit a candidate, including candidates judged not applicable: a not-applicable candidate is presented *with the grounds for its exclusion*, so the user sees why it was ruled out rather than wondering whether it was considered.

**Judgment rule (grounded in findings).** For each candidate, report exactly one applicability judgment, grounded in **at least one** detection result (a blocker ID, a `tech_stack` entry, or a Scoring_Dimension result):

| Judgment | Meaning |
|---|---|
| `applicable` | The detected stack and blockers satisfy the candidate's conditions as-is (after the modernization items common to the Rearchitect path) |
| `applicable_after_remediation` | The candidate becomes viable once specific listed modernization items are completed — name the items and the findings they resolve |
| `not_applicable` | A detected finding conflicts with a hard constraint of the candidate — name the finding and the constraint |

A judgment without a grounding finding is not a judgment — do not emit one. When the evidence needed to judge a candidate is undetermined, report the judgment as unsettled with the missing information named (see [Edge Cases](#applicability-cannot-be-settled)).

#### ECS Express Mode

An opinionated fast path (launched Nov 2025): from a container image plus two IAM roles, ECS provisions and manages the cluster, Fargate task definition, ALB, target groups, security groups, and autoscaling, with an AWS-provided HTTPS URL out of the box ([Express Mode announcement](https://aws.amazon.com/about-aws/whats-new/2025/11/announcing-amazon-ecs-express-mode/), [overview](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/express-service-overview.html)).

**Applicability conditions:**

- The workload is an HTTP/HTTPS web application or API fronted by a load balancer — Express Mode's task definition contract is a single main container with **one TCP port mapping** and Fargate compatibility.
- Fargate constraints apply transitively: Linux containers, no GPU, no privileged mode, no custom kernel.
- The team accepts AWS best-practice defaults (shared ALB, managed autoscaling, canary deployments) instead of fine-grained control over the ALB, networking, and task placement.

**Typical grounding:** *applicable* when the detected framework is a web stack (e.g. Spring Boot web starter, ASP.NET Core) and state findings are covered by listed items; *not_applicable* when the detected entry point is non-HTTP (batch workers, message consumers, protocols needing an NLB) or the deployable requires multiple exposed ports / sidecar containers — cite the `tech_stack` evidence that shows it.

#### ECS on Fargate

Serverless compute: each task runs in its own managed microVM; no instances to provision, patch, or scale. The default recommendation for standard long-running Linux services.

**Applicability conditions:**

- Linux containers with no GPU requirement — Fargate has **no GPU support** ([Fargate task/service considerations](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/fargate-tasks-services.html)).
- No privileged containers, custom AMI/kernel, or host device access.
- Task resource needs fit within Fargate task-size limits.
- OS-specific dependencies (the `os_specific_api` blocker category) have been removed or ported — the Rearchitect path targets modern Linux containers; Windows-only API dependencies must be resolved by a porting item first (the Windows-container route without code changes is a Replatform variant, covered in [replatform-path.md](replatform-path)).

**Typical grounding:** *applicable* for most stateless-after-remediation web and service workloads; *applicable_after_remediation* when `os_specific_api` or `process_model` blockers exist and are mapped to listed items; *not_applicable* when the stack evidences GPU/specialized-hardware dependence — cite the dependency evidence.

#### ECS Managed Instances

Fully managed EC2 capacity for ECS (GA since Sept 2025, all commercial Regions since Oct 2025): AWS provisions, patches, and replaces the instances (drain-and-replace on a 14–21 day lifecycle) while you keep EC2 instance-type flexibility — including GPU-accelerated, network-optimized, and burstable families ([Managed Instances docs](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ManagedInstances.html), [FAQs](https://aws.amazon.com/ecs/managed-instances/faqs/)).

**Applicability conditions:**

- The workload benefits from EC2 instance-type flexibility (GPU, specific families, resource footprints beyond Fargate limits) or Spot/Reserved capacity economics, without the team wanting to operate a fleet.
- Linux containers on **Bottlerocket only** (X86_64 / ARM64) — no custom AMI/kernel, no Windows; OS-specific dependencies must be resolved by porting items, as with Fargate.
- `awsvpc` or `host` network mode (no `bridge`).
- Tasks tolerate being cycled by the 14–21 day drain-and-replace patching lifecycle — which makes the graceful-shutdown modernization item a first-class prerequisite ([Managed Instances patching](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/managed-instances-patching.html)).
- Not available in the China Regions.

**Typical grounding:** *applicable* when findings evidence resource or hardware needs Fargate cannot serve (cite the `tech_stack` or dependency evidence); *applicable_after_remediation* when graceful-shutdown or state findings must be resolved first (instance cycling makes unhandled shutdown a live risk, not a theoretical one); *not_applicable* when the deployment must land in a China Region or genuinely requires a custom AMI/kernel — the latter is also a signal to revisit the Replatform path (ECS on EC2), which the report's both-strategies comparison already presents.

### Modernization Item Catalog and Mapping Rules

**Catalog (minimum consideration set).** Every Rearchitect assessment considers **at least** these five item categories. The catalog defines what to look for; it does not license listing an item without evidence.

| Catalog category | Listed when — corresponding detection results | What the item covers |
|---|---|---|
| **State externalization** | Blockers of category `local_state` or `in_process_session`; a low-scoring `state_management` dimension result | Move authoritative state out of the task: sessions to an external store, persisted business data to external data stores or EFS-backed storage |
| **Configuration externalization (environment variables)** | Environment-specific values baked into the artifact — the endpoint portion of `hardcoded_credentials` blockers; a low-scoring `config_externalization` dimension result | Replace build-time environment values with environment variables / externalized configuration so one artifact moves across environments |
| **Secret externalization** | The credential portion of `hardcoded_credentials` blockers | Move secrets out of code and committed configuration into a secret store injected at runtime (never echo any part of a detected credential value — the secrecy rule from blocker detection carries through) |
| **Health check endpoint addition** | Source_Analysis evidence that health monitoring is host- or application-server-based, or that the examined routing surface has no dedicated health endpoint (`tech_stack.app_servers` entries; dimension evidence naming the routing artifacts examined) | Add a dedicated liveness/readiness endpoint the load balancer and ECS health checks can target |
| **Graceful shutdown support** | Blockers of category `process_model` (host-supervised lifecycle); `in_process_session` findings (session loss on task replacement); evidence that the entry point has no termination-signal handling | Handle SIGTERM: stop accepting work, drain in-flight requests, release resources within the stop timeout — a prerequisite for task cycling on every candidate, and non-negotiable under Managed Instances' instance lifecycle |

**Mapping rules:**

1. **No finding → no item.** An item is listed **only** when at least one corresponding detection result exists — a blocker ID or a Scoring_Dimension result (with its evidence path). Never list a catalog item "for completeness" or from general expectations about legacy applications. Conversely, effort classification and evidence mapping apply only to listed items — never attach either to an item that is not listed.
2. **Every listed item carries its grounding.** Each item maps to at least one detection result (blocker ID such as `BLK-003`, or a dimension result with its evidence path) and **exactly one** effort tier from the [scale below](#effort-scale-single-definition).
3. **Coverage of remediation-requiring blockers.** Every blocker that blocker detection classified as *acceptable under Replatform but requiring remediation under Rearchitect* (`remediation_class: replatform_ok`) **must** map to at least one listed item. Blockers classified `must_fix` require resolution under *either* strategy — under Rearchitect they are likewise mapped to items (and the report notes they gate Replatform too). Before assembling the output, verify the mapping is complete: an unmapped `replatform_ok` blocker is an assembly error — fix the item list, do not ship the gap.
4. **Beyond-catalog items.** A finding that requires remediation under Rearchitect but fits none of the five catalog categories still becomes an item — with a descriptive name, its grounding, and an effort tier. The catalog is a floor, not a ceiling.
5. **Zero items is an explicit statement.** If no blocker requires remediation and no dimension result calls for remediation, report **explicitly** that the application can move to the Rearchitect path **with zero modernization items** — never leave the section empty or silent.

### Effort Scale (Single Definition)

Every listed modernization item — including optional framework-migration items — receives **exactly one** of these three tiers. This section is the sole definition of the scale; the both-strategies comparison mandated by the recommendation rules ([scoring-and-recommendation.md](scoring-and-recommendation), "Always Present Both Strategies") classifies each strategy's remediation effort on **this same scale**, by reference to this section.

| Tier | Definition | Recognizing it |
|---|---|---|
| **small** | **Localized configuration/code changes** — confined to a few files, no interface or structural change | Externalizing a handful of hardcoded values, adding a health endpoint to an existing controller surface, registering a shutdown hook in one entry point |
| **medium** | **Cross-cutting but mechanical changes** — spans layers or modules, but each change applies a known pattern; no design change | Sweeping all configuration reads onto an environment-variable provider, replacing session-write call sites with an external session store across controllers, `javax` → `jakarta` namespace migration |
| **large** | **Architecture/framework-level changes** — alters the application's structure, framework, or design | Framework replacement (Struts → Spring Boot), re-architecting authoritative in-memory state, decomposing a host-supervised multi-process arrangement |

**Assignment discipline:** classify from the actual scope of the grounding findings — the number and spread of evidence paths, whether the change crosses module boundaries, and whether any design decision is required — not from the category name (state externalization *can* be small when a single misplaced cache write is the only finding). When AWS Transform is applicable to an item, the tier still reflects the manual effort; the potential reduction is expressed as a note (next sections), never by silently reclassifying the tier.

### Framework Migration Options

When the detected framework is in the legacy classification (per the modernity ladder in [scoring-and-recommendation.md](scoring-and-recommendation)) and an **established migration path to a successor framework exists**, present the framework migration as an **optional** modernization item — never a mandatory one — with its approximate effort tier. The Rearchitect path remains viable without it: containerizing on the legacy framework and modernizing state/config/secrets is a legitimate Rearchitect outcome.

**Established paths:**

| From (detected) | To | Approximate effort | Notes |
|---|---|---|---|
| Struts (1 / 2) | Spring Boot | large | Struts 1 is EOL ([announcement](https://struts.apache.org/struts1eol-announcement.html)); migration is a rewrite of the web layer onto Spring MVC idioms |
| Spring Framework (non-Boot) | Spring Boot | medium | Mechanical adoption of starters and auto-configuration; application code largely survives |
| Jakarta EE / Java EE (`javax.*`) | Jakarta EE 10+ (`jakarta.*`) | medium | Namespace migration plus dependency and server alignment ([Jakarta EE 9 namespace change](https://jakarta.ee/blogs/javax-jakartaee-namespace-ecosystem-progress/)) |
| ASP.NET MVC (.NET Framework) | ASP.NET Core | large | Established Microsoft path ([migration guide](https://learn.microsoft.com/en-us/aspnet/core/migration/mvc)); AWS Transform automates much of it (below) |
| ASP.NET Web Forms | ASP.NET Core (Blazor) | large | No direct successor; documented route is UI conversion to Blazor ([Blazor for Web Forms developers](https://learn.microsoft.com/en-us/dotnet/architecture/blazor-for-web-forms-developers/)); AWS Transform covers Web Forms UI → Blazor Server |
| WCF | CoreWCF | medium | Community/Microsoft-supported compatibility path ([CoreWCF 1.0 announcement](https://devblogs.microsoft.com/dotnet/corewcf-v1-released/)); a gRPC redesign is the *large* alternative |

**Application-server migration paths.** The same optional-item rule applies to **application servers**: when tech stack detection reports a vendor application server with an established, vendor-documented migration path to a container-native successor, present the server migration as an optional modernization item with its approximate effort — triggered by the `tech_stack.app_servers` detection rather than the modernity ladder:

| From (detected server) | To | Approximate effort | Notes |
|---|---|---|---|
| WebSphere Application Server traditional (tWAS) | WebSphere Liberty / Open Liberty | medium | IBM-documented modernization path ([modernizing to Liberty](https://developer.ibm.com/learningpaths/app-mod-liberty/)); converts the cell/profile configuration model to Liberty's `server.xml` feature configuration and replaces proprietary `com.ibm.websphere.*` / `com.ibm.wsspi.*` / CommonJ API usage with spec or MicroProfile equivalents. Effort scales with the code-level coupling depth from tech stack detection: descriptor-only apps are genuinely *medium* (mostly mechanical config conversion); heavy proprietary-API usage pushes toward *large*. **IBM assessment tooling** automates the readiness analysis — IBM Cloud Transformation Advisor and the Migration Toolkit for Application Binaries (binary scanner) report Liberty compatibility, flag proprietary-API usage, and estimate effort per application; present them as optional accelerators (assessment-side tooling — running them is the user's action, and code changes stay behind the Execution_Gate). Note: traditional WAS entitlement includes Liberty entitlement ([Liberty licensing](https://www.ibm.com/docs/en/was-liberty/base?topic=overview-licensing-liberty)), and Open Liberty is open source — the server migration typically *removes* the commercial-server licensing finding |
| WebSphere traditional / WebLogic-hosted Java EE app | Jakarta EE 10+ on a container-native runtime (Liberty, Tomcat where the API surface fits) | medium | The `javax` → `jakarta` row above compounds with the server move; treat them as one coordinated item when both apply, since the target Liberty feature level fixes the namespace generation |

Combining rule: when a tWAS-hosted app also carries ladder-level framework findings (e.g. Struts on tWAS), the server-migration item and the framework-migration item are **separate optional items** — each with its own effort tier and grounding — because either can be adopted without the other (Liberty runs Struts-era WARs; Spring Boot on tWAS is rare but the reverse adoption order is real).

**No established path (report, don't invent).** If the detected framework is legacy but no established successor path exists (no documented vendor or community migration route), report **explicitly** that a framework-migration option cannot be offered, with the reason (no established path for the detected framework), and **still present the Rearchitect path itself** — through the compute candidates and the non-framework modernization items. The absence of a framework option never suppresses the path.

### AWS Transform Applicability Guidance

AWS Transform is presented in the assessment as an **optional accelerator recommendation only** — with its automation scope — attached to the modernization items it matches. Actual transformation is executed exclusively by the code transformation module ([code-transformation.md](code-transformation)) after Execution_Gate passage; this module never starts a transformation, never proposes a job, and never treats Transform adoption as decided.

**Matching items and automation scope:**

| Modernization item | AWS Transform applicability | Automation scope to present |
|---|---|---|
| EOL Java / Node.js / Python runtime version upgrade | Out-of-the-box transformation definitions for language version upgrades | Dependency and API updates for the version jump; residual work (documented gaps) remains with the agent or the user ([AWS Transform user guide](https://docs.aws.amazon.com/transform/latest/userguide/)) |
| .NET Framework → .NET 8 (LTS) / .NET 10 porting (including the ASP.NET MVC → ASP.NET Core and Web Forms UI → Blazor Server framework items) | AWS Transform for .NET — sources .NET Framework 3.5+, .NET Core 3.1, .NET 5.x+; targets .NET 8 / .NET 10, C# only | Entity Framework / ADO.NET migration, MVC Razor Views → ASP.NET Core Razor Views, NuGet version resolution, Web Forms UI → Blazor Server ([AWS Transform for .NET](https://docs.aws.amazon.com/transform/latest/userguide/dotnet.html)) |

**Annotation rules:**

- Attach the applicability as the item's `aws_transform_applicability` string — naming the matching source/target versions and the automation scope. Items with no matching transformation get `null`, never a speculative claim.
- Add the **effort-reduction note**: when AWS Transform is applicable and adopted, the item's effort tier may effectively drop (e.g. a *large* .NET port trending toward *medium* for the automated portion). The classified tier itself stays the manual-effort judgment; the note is presentation, not reclassification.
- Coverage claims are fast-moving: before asserting them in a report, re-verify against the live documentation URLs above (the technical-freshness directive in [code-transformation.md](code-transformation) applies here too).

### Delegation to ecs-architect

Whenever the compute-model candidates are presented, the report **must state** that the final deployment-model detailed design — **capacity provider strategy, task sizing, and network design** — is delegated to the `ecs-architect` sibling skill. This module stops at candidates, applicability conditions, and applicability judgments; it produces **no** concrete design values — no capacity provider strategies, no CPU/memory numbers, no subnet, security-group, or load-balancer design — in the Modernization_Report. A user request for those specifics gets the candidate presentation plus a named delegation to `ecs-architect`, not the design itself.

---

## Output Schema

This module produces the `rearchitect_path` block — the source data for the report's "Rearchitect path details" section. Hold it in conversation context; the assessment phase writes no intermediate files.

```yaml
rearchitect_path:
  compute_candidates:              # ALWAYS exactly three entries — never a subset
    - name: ecs_express_mode | ecs_fargate | ecs_managed_instances
      applicability: applicable | applicable_after_remediation | not_applicable | unsettled
      conditions: [string]         # the applicability conditions presented for this candidate
      grounds: [{finding: string}] # >= 1 blocker id / tech_stack entry / dimension result;
                                   # for unsettled: the missing information instead
      remediation_items: [string]  # items that close the gap (applicable_after_remediation only)
  modernization_items:
    - item: string                 # descriptive item name
      catalog_category: state_externalization | config_env_vars | secret_externalization |
                        health_check_endpoint | graceful_shutdown | framework_migration | other
      optional: bool               # true for framework-migration options; false otherwise
      evidence: [{path_or_finding: string}]   # >= 1 — blocker id or dimension result w/ path
      effort: small | medium | large          # exactly one tier per listed item
      effort_approximate: bool     # true for framework-migration options (approximate tier)
      aws_transform_applicability: string | null
                                   # matching source/target versions + automation scope,
                                   # with the effort-reduction note; null when not applicable
  blocker_coverage:
    remediation_blockers: [string] # ids of all replatform_ok blockers (+ must_fix, which gate
                                   # both strategies) — the set that must be covered
    unmapped: []                   # MUST be empty; a non-empty list is an assembly error
  no_items: bool                   # true -> the explicit zero-item statement is mandatory
  framework_migration_note: string | null
                                   # the no-established-path report when applicable; null otherwise
  delegation_note: string          # REQUIRED: the ecs-architect delegation statement
                                   # (capacity provider strategy / task sizing / network design)
```

**Reporting invariants:**

- `compute_candidates` always contains exactly the three named candidates, each with `conditions` and grounded judgment.
- Every `modernization_items` entry has ≥ 1 evidence entry and exactly one `effort` tier; no entry exists without a corresponding detection result.
- `blocker_coverage.unmapped` is empty in every shipped output.
- `no_items: true` and a non-empty `modernization_items` list are mutually exclusive; `no_items: true` obliges the explicit statement in the report.
- `delegation_note` is always present — the Rearchitect section of the report never appears without it.
- No evidence entry or item description contains any part of a credential value.

---

## Edge Cases

### Zero modernization items

No remediation-requiring blocker and no remediation-requiring dimension result: set `no_items: true`, list nothing, and report explicitly that the application can move to the Rearchitect path with zero modernization items. Do not pad the list with speculative improvements to make the section look substantial.

### No Fit_Score / grey-zone recommendation

The Rearchitect path is presented **regardless** of the recommendation outcome — firm Rearchitect, firm Replatform, grey zone, or no score at all (the report always carries both strategies). When the score was computed under renormalization or could not be computed, the confidence notes from the recommendation carry through; this module does not re-judge confidence.

### must_fix blockers present

Blockers classified `must_fix` gate both strategies. Map them to modernization items like any other remediation-requiring blocker, and note in the item that it must be resolved even under Replatform — the item is not an argument for one strategy over the other.

### Windows-only dependencies detected

`os_specific_api` blockers evidencing Windows-only APIs make all three candidates `applicable_after_remediation` at best: the porting item (typically with AWS Transform for .NET applicability) is the gap-closing item. The no-code-change Windows container route belongs to the Replatform path ([replatform-path.md](replatform-path)) — reference it, do not duplicate it here.

### Applicability cannot be settled

When the evidence needed to judge a candidate is undetermined (e.g. the deployable's entry-point protocol could not be established), report the candidate's judgment as `unsettled` with the missing information named — never guess a judgment. The candidate still appears with its conditions.

### Legacy framework with no established migration path

Report that no framework-migration option can be offered, name the detected framework and the reason (no established successor path), set `framework_migration_note`, and present the Rearchitect path through the remaining items and candidates. See [Framework Migration Options](#framework-migration-options).

### User asks for the detailed design

Present the candidates and applicability as usual, include the delegation note, and route the capacity-provider-strategy / task-sizing / network-design request to `ecs-architect` by name. Do not produce design values "just this once".

### Partial analysis

Items and judgments are derived from the readable evidence as usual; the partial-analysis state propagates to the report's incomplete-analysis section. A candidate whose decisive evidence fell inside excluded paths is `unsettled`, not guessed.

---

## Sources

- Announcing Amazon ECS Express Mode (Nov 2025): https://aws.amazon.com/about-aws/whats-new/2025/11/announcing-amazon-ecs-express-mode/
- Amazon ECS Express Mode overview (task definition contract, managed resources): https://docs.aws.amazon.com/AmazonECS/latest/developerguide/express-service-overview.html
- Fargate task/service considerations (no GPU, task sizing): https://docs.aws.amazon.com/AmazonECS/latest/developerguide/fargate-tasks-services.html
- Architect for Amazon ECS Managed Instances (Bottlerocket-only, networking): https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ManagedInstances.html
- Amazon ECS Managed Instances FAQs (Region availability, pricing model): https://aws.amazon.com/ecs/managed-instances/faqs/
- Managed Instances patching (14–21 day drain-and-replace lifecycle): https://docs.aws.amazon.com/AmazonECS/latest/developerguide/managed-instances-patching.html
- AWS Transform for .NET (coverage: sources, targets, project types): https://docs.aws.amazon.com/transform/latest/userguide/dotnet.html
- AWS Transform user guide (language version upgrade transformation definitions): https://docs.aws.amazon.com/transform/latest/userguide/
- ASP.NET MVC → ASP.NET Core migration guide: https://learn.microsoft.com/en-us/aspnet/core/migration/mvc
- Blazor for ASP.NET Web Forms developers: https://learn.microsoft.com/en-us/dotnet/architecture/blazor-for-web-forms-developers/
- CoreWCF 1.0 release announcement: https://devblogs.microsoft.com/dotnet/corewcf-v1-released/
- IBM learning path — modernizing applications to use WebSphere Liberty: https://developer.ibm.com/learningpaths/app-mod-liberty/
- IBM Cloud Transformation Advisor: https://www.ibm.com/docs/en/cta — generated Liberty migration artifacts (`server.xml`, `pom.xml`, Containerfile, Application CR): https://www.ibm.com/docs/en/cta?topic=migration-artifacts
- Migration Toolkit for Application Binaries (binary scanner — Liberty readiness evaluation): https://www.ibm.com/support/pages/migration-toolkit-application-binaries
- Migrating applications to Liberty (IBM migration task hub): https://www.ibm.com/docs/en/was-liberty/base?topic=migrating-applications-liberty
- Licensing for WebSphere Application Server Liberty (traditional WAS entitlement includes Liberty entitlement): https://www.ibm.com/docs/en/was-liberty/base?topic=overview-licensing-liberty
- Apache Struts 1 end-of-life announcement: https://struts.apache.org/struts1eol-announcement.html
- Jakarta EE namespace migration (`javax` → `jakarta`): https://jakarta.ee/blogs/javax-jakartaee-namespace-ecosystem-progress/
- The Twelve-Factor App — config, processes, disposability (state, config, graceful shutdown items): https://12factor.net/config , https://12factor.net/processes , https://12factor.net/disposability
