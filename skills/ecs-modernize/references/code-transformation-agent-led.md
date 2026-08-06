# Module: Code Transformation — Agent-Executed Items

> **Part of:** [ecs-modernize](../SKILL.md)
> **Purpose:** Execute the Agent_Executed_Items of the Transformation_Plan — hands-on .NET Framework → modern .NET porting and Java / other runtime EOL upgrades — under strict working-location safety rails, an incremental change → verify → commit discipline, and honest verification reporting
> **Prerequisites:** **Execution_Gate passage** (Requirement 14) AND the **"code transformation start" action-class confirmation** obtained via the process model in [code-transformation.md](code-transformation.md). This file is the second file of the code transformation module: the plan construction, augmentation determination, partitioning, and adoption logic live in code-transformation.md — this file holds the HOW for the items that plan routes to `execution: agent`

An **Agent_Executed_Item** is a work item of the single Transformation_Plan that Transform_Augmentation does not cover: AWS Transform unavailable, transformation type outside documented coverage, augmentation not adopted, or residual work an AWS Transform job left unfinished. Every such item is executed by the agent, inside the same plan, in plan order — interleaved with Transform-augmented items as the order dictates. This file supplies the porting and upgrade knowledge, the safety rails that keep the original source untouched, and the verification and reporting rules for that execution.

Like its companion, this knowledge is application-level and orchestrator-neutral: it describes how code is ported and upgraded, not where it will be deployed.

## Table of Contents

- [Inputs](#inputs)
- [Working Location — Safety Rails](#working-location--safety-rails)
  - [The Approved Working Location](#the-approved-working-location)
  - [Working-Location Options After Transform_Augmentation Completion](#working-location-options-after-transform_augmentation-completion)
  - [Repository Safety Invariants](#repository-safety-invariants)
- [Execution Discipline — Item by Item, Small Steps](#execution-discipline--item-by-item-small-steps)
- [Porting Knowledge — .NET Framework → Modern .NET](#porting-knowledge--net-framework--modern-net)
  - [Workflow Order](#workflow-order)
  - [Step 1 — Project Conversion to SDK Style](#step-1--project-conversion-to-sdk-style)
  - [Step 2 — packages.config → PackageReference](#step-2--packagesconfig--packagereference)
  - [Step 3 — web.config → appsettings.json](#step-3--webconfig--appsettingsjson)
  - [Step 4 — Global.asax → Program.cs and the Middleware Pipeline](#step-4--globalasax--programcs-and-the-middleware-pipeline)
  - [Step 5 — System.Web Replacement Map](#step-5--systemweb-replacement-map)
  - [Step 6 — IIS → Kestrel](#step-6--iis--kestrel)
  - [Step 7 — Windows API Dependencies and .NET Alternatives](#step-7--windows-api-dependencies-and-net-alternatives)
- [Porting Knowledge — Java EOL Upgrades](#porting-knowledge--java-eol-upgrades)
  - [javax → jakarta Namespace Migration](#javax--jakarta-namespace-migration)
  - [Dependency Update Ordering](#dependency-update-ordering)
  - [Build Plugin Updates](#build-plugin-updates)
  - [JDK Behavioral and Removal Changes](#jdk-behavioral-and-removal-changes)
- [Other Runtime Upgrades — Node.js / Python](#other-runtime-upgrades--nodejs--python)
- [Verification](#verification)
  - [Local Verifiability](#local-verifiability)
  - [Per-Item Build and Test Verification](#per-item-build-and-test-verification)
  - [Verification Failure — Report, Block, Log](#verification-failure--report-block-log)
  - [When Local Verification Is Not Possible — Honest Reporting](#when-local-verification-is-not-possible--honest-reporting)
- [Interruption and Incompletion](#interruption-and-incompletion)
- [Plan Completion — Mandatory Human Review, No Merge](#plan-completion--mandatory-human-review-no-merge)
- [Output Schema](#output-schema)
- [Edge Cases](#edge-cases)
- [Sources](#sources)

---

## Inputs

- **The partitioned Transformation_Plan** (required) — from [code-transformation.md](code-transformation.md): the items with `execution: agent`, each carrying its per-item reason (not applicable / not adopted / Transform residual work), in plan order.
- **The "code transformation start" confirmation** (required) — the Requirement 14 action-class confirmation, whose presented content included the working branch / working directory for Agent_Executed_Items. No item in this file executes before it, and a change to the presented content (including the working location) requires re-confirmation before execution continues under it.
- **The user-approved working location** (required) — the working branch or working directory the user approved. Where Transform_Augmentation has completed, the approved location may be a Transform target branch or a branch derived from one (see [working-location options](#working-location-options-after-transform_augmentation-completion)).
- **Host OS and toolchain facts** — determine local verifiability per dimension (b) of the [proposal dimensions](code-transformation.md#the-four-proposal-dimensions) (language × host OS × toolchain presence). Established by inspection of the execution host and by asking the user where inspection cannot settle it.
- **Source_Analysis results** (when available) — `tech_stack` and `blockers` inform which porting steps apply (e.g. which `System.Web` surfaces exist, which OS-specific APIs need alternatives). When the assessment was skipped, the user-specified targets and the code itself are the evidence base.

---

## Working Location — Safety Rails

These rails implement Requirements 11.9, 11.17, 15.17, and 15.18. They are absolute: no porting step, however small, operates outside them.

### The Approved Working Location

- **All transformation operations are confined to the user-approved working branch or working directory.** File edits, file creation, dependency changes, build outputs under the working tree — everything this module does to code happens inside that approved location and nowhere else.
- **The original source branch is never modified.** Files that existed under the target source directory at the start of Migration_Execution are never directly edited; the agent works on a code copy inside the approved location (new branch checked out from the source, or a copied working directory), consistent with Requirement 11.9. Files the agent itself created in the approved location during Migration_Execution may be freely modified.
- **The working location is part of the confirmed content.** It was presented at the "code transformation start" confirmation; changing it (a different branch, a different directory) changes the confirmed content and requires re-confirmation before any pending item executes under the new location.

### Working-Location Options After Transform_Augmentation Completion

When one or more Transform_Augmentation jobs have completed and their target branches exist (Requirement 15.18):

1. **Present the working-location options for the remaining Agent_Executed_Items**, including ALL of:
   - **each completed job's target branch** (every target branch when multiple jobs completed — enumerate them by name);
   - **a new branch derived from any of those target branches**;
   - the previously approved working branch / working directory of the [rule above](#the-approved-working-location).
2. **Continue on a target-branch-derived option only on the user's approval.** If the user approves a target branch or a derived branch, subsequent Agent_Executed_Items (typically the residual work the job left unfinished) execute on that approved branch.
3. **If the user approves none of the target-branch-derived options**, continue in the previously approved working branch / working directory.
4. **In every case, the original source branch remains unmodified** — the choice is only ever between approved non-source locations.

Working on the Transform target branch is usually the right default to *propose* for residual work (the ported code is already there), but it is never assumed: the approval is explicit, and it is part of the confirmed content per the re-confirmation rule.

### Repository Safety Invariants

Per Requirement 11.17, at all times, regardless of working location:

- **No deletion of existing branches.**
- **No force push to existing branches.**
- **No commit-history rewriting** (no rebase of pushed history, no amend of commits that predate this execution, no filter-branch/filter-repo).

Checkpoint commits are ordinary forward commits on the working branch. If a checkpoint needs correction, make a new commit — never rewrite.

---

## Execution Discipline — Item by Item, Small Steps

Requirement 15.19 makes incremental execution mandatory. The discipline:

1. **Follow the plan order.** Execute Agent_Executed_Items in the Transformation_Plan's order — one work item at a time, never batching several items into one sweep. Items are interleaved with Transform-augmented items as the plan dictates.
2. **Inside each work item, work in small increments**: make a small, coherent change (one project conversion, one namespace sweep, one config migration) → verify it (build; tests where available) → commit it. Never accumulate a large uncommitted diff: a failed verification should implicate a small change, not an afternoon of edits.
3. **Verify at item completion.** When local build verification is possible ([local verifiability](#local-verifiability)), run the build at each work item's completion — and the tests, when the codebase has runnable tests. An item is not "done" until its completion verification has run (or been honestly reported as not locally possible).
4. **Record a checkpoint commit at each item's completion** on the working branch, and record its identifier (commit hash) in the item's result and the Execution_Log. Checkpoints are the recovery points that [interruption handling](#interruption-and-incompletion) preserves.
5. **Log every action.** Item start, each verification result, each checkpoint commit — recorded in the Execution_Log before the next action starts, per the logging rules in [code-transformation.md](code-transformation.md#execution-ordering-confirmations-and-logging) (storage forms and save-failure fallback per the canonical [deploy-verify-handoff.md — Execution_Log Rules](deploy-verify-handoff.md#execution_log-rules)).

**Why this order and granularity:** plan order preserves the dependency ordering the plan encoded (shared libraries before consumers; base port before API replacements); small increments keep every verification failure attributable and every checkpoint restorable; per-item checkpoints make interruption cheap instead of catastrophic.

---

## Porting Knowledge — .NET Framework → Modern .NET

The workflow for a ".NET Framework → .NET 8 LTS (or later)" work item. Verify current tooling and target-version guidance against the live Microsoft porting documentation before relying on version-specific details — the same freshness posture as the companion file's [Technical Freshness Directive](code-transformation.md#technical-freshness-directive).

### Workflow Order

```
1. Project conversion to SDK style        (per project, dependency order:
2. packages.config -> PackageReference     libraries first, then apps)
3. web.config -> appsettings.json
4. Global.asax -> Program.cs / middleware
5. System.Web surface replacement          (the largest step for web apps)
6. IIS -> Kestrel hosting
7. Windows API dependencies -> .NET alternatives
```

Steps 1–2 modernize the project format and restore model *while still targeting .NET Framework where possible* — they are verifiable on their own and make excellent early checkpoints. Steps 3–6 are the web-application port proper. Step 7 addresses the `blockers` entries with `os_specific_api` category and runs after the base port, per the plan's ordering rules. For multi-project solutions, run each step across projects in **dependency order**: class libraries first (consider `netstandard2.0` as an intermediate target where both old and new consumers must coexist), then executables and web apps.

Tooling: the **.NET Upgrade Assistant** automates parts of steps 1–2 and some source rewrites; **try-convert** (its archived predecessor) handled SDK-style conversion only. Use them as accelerators inside the working branch when available — their output goes through the same verify-and-checkpoint discipline as manual edits. The **Platform Compatibility Analyzer** (`CA1416`) and the upgrade tools' analysis phase identify Windows-only API usage for step 7.

### Step 1 — Project Conversion to SDK Style

Convert each `.csproj` from the legacy verbose format to the SDK-style format:

- Replace the legacy header with `<Project Sdk="Microsoft.NET.Sdk">` (web apps: `Microsoft.NET.Sdk.Web`).
- Remove explicit `<Compile>` globs (SDK-style projects include sources by default), `packages.config`-era `<Reference>` hint paths, and `AssemblyInfo.cs` attributes that the SDK now generates (or set `<GenerateAssemblyInfo>false</GenerateAssemblyInfo>` initially to defer that change).
- Set `<TargetFramework>`: an SDK-style project can still target `net48` — converting format before retargeting keeps this step independently buildable and verifiable. Retarget to `net8.0` (or the approved target) when the port steps proper begin. Multi-targeting (`<TargetFrameworks>net48;net8.0</TargetFrameworks>`) is a useful transitional state for libraries.

Checkpoint after each converted project builds.

### Step 2 — packages.config → PackageReference

- Migrate each project's `packages.config` entries to `<PackageReference>` items in the `.csproj` (Visual Studio offers a built-in migrator; manual migration is a mechanical rewrite).
- PackageReference resolves **transitive dependencies automatically** — remove packages that were only ever transitive; keep only direct dependencies.
- Delete the `packages/` folder reliance; restore now uses the global package cache.
- Watch for packages that relied on `install.ps1` scripts or content-file injection — PackageReference does not run install scripts; such packages may need replacement or manual equivalent steps.
- Update package versions toward the target framework's compatible versions as part of the retarget (e.g. `Newtonsoft.Json` stays; `Microsoft.AspNet.*` packages are *replaced*, not upgraded — see step 5).

### Step 3 — web.config → appsettings.json

| web.config construct | Modern .NET equivalent |
|---|---|
| `<appSettings>` key/values | `appsettings.json` sections + `IConfiguration` (`builder.Configuration["Key"]`), strongly typed via the options pattern (`IOptions<T>`) |
| `<connectionStrings>` | `ConnectionStrings` section in `appsettings.json`; `IConfiguration.GetConnectionString(...)` |
| `<system.web>` (compilation, httpRuntime, sessionState, authentication) | No direct equivalent — behavior moves to Program.cs service/middleware configuration (step 4/5) |
| `<system.webServer>` (modules, handlers, rewrite) | Middleware pipeline; URL Rewriting Middleware for rewrite rules |
| Config transforms (`web.Release.config`) | Environment-specific files (`appsettings.Production.json`) + environment variables |
| `ConfigurationManager.AppSettings` call sites | Inject `IConfiguration` / `IOptions<T>`; avoid the static-access pattern |

Secrets discovered in `web.config` during migration are **relocated, never transcribed into the report or log**: point the user to environment variables or a secrets store, and per the all-phase invariant, never write a detected credential value anywhere — not in generated files' comments, not in the Execution_Log, not in conversation output.

### Step 4 — Global.asax → Program.cs and the Middleware Pipeline

| Global.asax member | Modern .NET equivalent |
|---|---|
| `Application_Start` (route/filter/bundle registration) | Program.cs: `builder.Services.Add*` registrations + `app.Map*` endpoint routing |
| `Application_BeginRequest` / `EndRequest` | Custom middleware (`app.Use(async (ctx, next) => ...)`) placed at the pipeline position matching the old event order |
| `Application_Error` | `app.UseExceptionHandler(...)` / `UseStatusCodePages` |
| `Session_Start` / `Session_End` | `AddSession()` + session middleware; `Session_End` has no equivalent (design around it) |
| HttpModules (`<system.webServer><modules>`) | Middleware classes registered in pipeline order |
| HttpHandlers (`.ashx`, custom handlers) | Endpoint routing (`app.MapGet/MapPost`) or minimal APIs; note `.ashx` is also a documented AWS Transform gap — it commonly arrives here as residual work |

### Step 5 — System.Web Replacement Map

The core reference for porting ASP.NET (System.Web-based) code:

| System.Web surface | Modern .NET replacement | Notes |
|---|---|---|
| `System.Web.Mvc` (ASP.NET MVC 5) | ASP.NET Core MVC (`Microsoft.AspNetCore.Mvc`) | Controllers/actions port with attribute changes (`HttpGet` namespaces, `ActionResult` → `IActionResult`); Razor views largely port; HtmlHelpers partially → Tag Helpers |
| `System.Web.Http` (Web API 2) | ASP.NET Core controllers (`[ApiController]`) | `ApiController` base → `ControllerBase`; message handlers → middleware; `HttpResponseMessage` returns → typed results |
| Web Forms (`.aspx`, code-behind) | No direct port — Blazor or Razor Pages rewrite | Page-lifecycle and ViewState models have no equivalent; treat as a rewrite work item, sized separately |
| `HttpContext.Current` | Injected `IHttpContextAccessor` / `HttpContext` on controllers | Eliminate static access; the DI-injected context is request-scoped |
| `HttpRequest` / `HttpResponse` (System.Web) | `Microsoft.AspNetCore.Http` equivalents | Property names differ (`Request.QueryString` → `Request.Query`; streams instead of direct writes) |
| Session (`HttpSessionState`) | `ISession` via `AddSession()` + `app.UseSession()` | Values are byte/string based — object session state needs explicit serialization; distributed cache backing for multi-instance |
| `System.Web.Caching.Cache` | `IMemoryCache` / `IDistributedCache` | Choose distributed cache when the ECS target runs multiple tasks |
| `FormsAuthentication` | ASP.NET Core cookie authentication / ASP.NET Core Identity | Auth cookies are not compatible across the boundary; plan re-authentication or use System.Web adapters' shared-auth during incremental migration |
| `Membership` / `Roles` providers | ASP.NET Core Identity | Schema migration for existing user stores |
| `Server.MapPath` | `IWebHostEnvironment.ContentRootPath` / `WebRootPath` | |
| `HttpModules` / `HttpHandlers` | Middleware / endpoint routing | See step 4 |
| Bundling (`System.Web.Optimization`) | Build-time bundling (e.g. front-end toolchain) or static-file middleware | No runtime bundling equivalent |
| WCF service hosting (`System.ServiceModel`, `.svc`) | **CoreWCF** (community/Microsoft-supported port) or reshape to gRPC / REST | `.svc` hosting is also a documented AWS Transform gap; CoreWCF covers common bindings (BasicHttp, NetTcp) — check its coverage for the bindings actually used |

For large ASP.NET apps, Microsoft's **incremental migration** approach (YARP proxy + `Microsoft.AspNetCore.SystemWebAdapters`) allows routing migrated endpoints to the new app while the rest stays on .NET Framework — propose it as an option when a big-bang port of one item is too large to verify in increments.

### Step 6 — IIS → Kestrel

- The ported app self-hosts on **Kestrel**; `WebApplication.CreateBuilder` wires it by default. IIS-specific artifacts (`web.config` server sections, IIS modules) do not port.
- Responsibilities that IIS held move explicitly:
  - **TLS termination, compression, static files**: in the ECS target, typically an ALB / reverse proxy terminates TLS; static files via `UseStaticFiles`; compression via `UseResponseCompression` if not proxy-handled.
  - **Windows Authentication (NTLM/Kerberos via IIS)**: needs `Microsoft.AspNetCore.Authentication.Negotiate` on Windows hosts, or an auth redesign for Linux containers — surface this as a decision, not a silent change.
  - **App lifecycle (IIS app pool recycling, warmup)**: container orchestrator concerns now; health checks via `MapHealthChecks`.
- Listen address in containers: bind to `0.0.0.0` on the container port (`ASPNETCORE_URLS` / `UrlPrefixes`), never `localhost`.
- If the approved path keeps the app on IIS in Windows containers (Windows_Container_Path replatform without porting), this step does not apply — that path's knowledge lives in the Replatform module, not here.

### Step 7 — Windows API Dependencies and .NET Alternatives

Address the `blockers` entries (category `os_specific_api`) after the base port. Detection support: the **Windows Compatibility Pack** (`Microsoft.Windows.Compatibility`) makes many Windows-only APIs *compile* on modern .NET but throw `PlatformNotSupportedException` on Linux — it is a porting bridge, not a Linux fix. The Platform Compatibility Analyzer (`CA1416`) flags call sites.

| Windows-only dependency | .NET / cloud alternative |
|---|---|
| Registry access (`Microsoft.Win32.Registry`) | Configuration via `IConfiguration` (appsettings/env vars) or a parameter store |
| Windows Services (`ServiceBase`) | **Worker Service** template (`BackgroundService`); runs anywhere, container-friendly |
| `System.Drawing.Common` (Linux-unsupported since .NET 6) | `ImageSharp`, `SkiaSharp`, or `Microsoft.Maui.Graphics` |
| MSMQ (`System.Messaging`) | Amazon SQS, RabbitMQ, or other broker (no modern .NET MSMQ client) |
| DPAPI (`ProtectedData`) | ASP.NET Core Data Protection with a shared key ring (e.g. persisted to S3/SSM for multi-instance) |
| Windows Event Log | `ILogger` structured logging to stdout (container-native) → CloudWatch Logs |
| `System.DirectoryServices` (AD) | `System.DirectoryServices.Protocols` (cross-platform LDAP) or an identity-provider integration |
| COM interop / P/Invoke into Windows DLLs | No cross-platform equivalent — rewrite, isolate behind an interface on a Windows-hosted service, or keep the component on the Windows container path |
| WCF *client* usage | `System.ServiceModel.*` client packages (supported on modern .NET) — distinct from service hosting (step 5) |

Every item in this step that has no drop-in alternative is a **decision point for the user**, not a silent substitution: present the alternative, its behavioral difference, and let the approved plan govern.

---

## Porting Knowledge — Java EOL Upgrades

The workflow for "Java 8 (or other EOL version) → supported LTS" work items. The same incremental discipline applies: one increment (namespace sweep, one dependency group, one plugin) → build/test → checkpoint.

### javax → jakarta Namespace Migration

Java EE APIs moved to Jakarta EE; from **Jakarta EE 9** the package namespace changed `javax.*` → `jakarta.*` (e.g. `javax.servlet` → `jakarta.servlet`, `javax.persistence` → `jakarta.persistence`, `javax.validation` → `jakarta.validation`). This bites any upgrade that crosses the boundary — most prominently Spring Boot 2 → 3 (which requires Java 17 and Jakarta EE 9+) and Tomcat 9 → 10+.

- **Scope the sweep first**: grep the codebase for `javax.` imports and classify which are Jakarta-governed (servlet, persistence, validation, annotation, transaction, mail, JAX-B/JAX-WS…) versus which remain in the JDK (`javax.crypto`, `javax.net`, `javax.sql` stay — do NOT rename those).
- **Mechanical rewrites are automatable**: OpenRewrite's Jakarta/Spring Boot 3 recipes and the Eclipse Transformer perform the import/package rename plus descriptor updates; Apache Tomcat also ships a migration tool for webapps. Tool output goes through the same verify-and-checkpoint loop as manual edits.
- **Dependencies must move in lockstep**: a classpath mixing `javax.*` and `jakarta.*` variants of the same API fails at runtime — the namespace sweep and the dependency updates below land together (one work-item increment), not separately.

### Dependency Update Ordering

Update dependencies in this order — **BOM / parent first, then libraries**:

1. **Parent POM / platform BOM first** (e.g. `spring-boot-starter-parent` or the `spring-boot-dependencies` BOM; Jakarta EE platform BOM). The BOM re-pins the entire managed-dependency graph consistently; upgrading individual libraries before the BOM produces version skew.
2. **Framework and Jakarta-governed libraries next**, letting the BOM's managed versions apply — remove explicit `<version>` overrides that now conflict with the BOM.
3. **Standalone third-party libraries last**, upgraded to versions compatible with the new JDK and (where applicable) the jakarta namespace.
4. **Rebuild and run tests after each group** — not once at the end. Dependency-order violations surface as `NoClassDefFoundError` / `NoSuchMethodError` at test time; a per-group checkpoint isolates which group introduced them.

For multi-module builds, the same rule fractally: the root/parent module's management sections first, then leaf modules in dependency order.

### Build Plugin Updates

Old plugin versions fail on new JDKs before the application code even compiles — update them early:

| Plugin | What to update and why |
|---|---|
| `maven-compiler-plugin` | Recent version; switch `<source>/<target>` to `<release>` (correct cross-compilation against the new JDK's API); set the target release (e.g. 17, 21) |
| `maven-surefire-plugin` / `failsafe` | Old versions break on the module system and newer JDK internals; recent versions required for tests to run at all |
| `maven-enforcer-plugin` | Update `requireJavaVersion` rules to the new floor |
| Bytecode-touching plugins/libs (Jacoco, Lombok, ASM-based, Mockito/ByteBuddy) | Each has a minimum version per JDK bytecode level — upgrade before interpreting "weird" verifier or agent errors |
| Gradle builds | The Gradle version itself gates JDK support — upgrade the wrapper first, then the toolchain (`java.toolchain.languageVersion`), then plugins |

### JDK Behavioral and Removal Changes

Crossing Java 8 → 11+ removes APIs the code may silently depend on:

- **Java EE modules removed from the JDK (Java 11)**: JAXB (`java.xml.bind`), JAX-WS, `javax.annotation` (`@PostConstruct`), `javax.activation`, CORBA — add them back as explicit dependencies (their Jakarta artifacts, matching the namespace decision above).
- **Strong encapsulation of JDK internals (Java 16+)**: illegal reflective access now fails by default; `--add-opens` is a stopgap, upgrading the offending library is the fix.
- **Removals in later JDKs**: SecurityManager deprecation/degradation, Nashorn removal (15), Applet API, `Thread.stop` removal (20+) — check against the Oracle/OpenJDK migration guide for the specific source → target pair.
- Consult the target JDK's official migration guide per hop; do not assume 8 → 17 issues equal 8 → 11 issues plus 11 → 17 issues found separately.

---

## Other Runtime Upgrades — Node.js / Python

Node.js and Python EOL upgrades follow the same discipline (plan order, small increments, per-increment verify, checkpoint commits) with lighter mechanics: engine/interpreter floor updates (`package.json` `engines`, `pyproject.toml` `requires-python`), dependency-tree upgrades against the new runtime (lockfile regeneration, deprecation warnings as the worklist), and removal checks against the runtime's release notes. Local verifiability is simply toolchain presence — both are cross-platform. The verification, failure-handling, interruption, and review rules of this file apply unchanged.

---

## Verification

### Local Verifiability

Determined per dimension (b) of [code-transformation.md](code-transformation.md#the-four-proposal-dimensions) — mechanical: language × host OS × toolchain presence. The pivotal asymmetry for .NET items:

- The **.NET Framework baseline cannot be built on a non-Windows host** (MSBuild + .NET Framework reference assemblies + often IIS/Windows deps).
- The **ported, cross-platform .NET result is verifiable with the dotnet SDK on any host**.

So on a Linux/macOS host, a .NET port typically has an **unverifiable "before" and a verifiable "after"**: the agent cannot demonstrate baseline behavior locally, but can build/test the ported output as soon as the retarget compiles. Java / Node.js / Python items are locally verifiable wherever the matching toolchain (JDK + Maven/Gradle, Node, Python) is present. Record the determination per item — it drives which of the two paths below applies.

### Per-Item Build and Test Verification

When local verification is possible (Requirement 15.19):

- **Build verification at each work item's completion** — the full compile of the affected project(s), in the working location.
- **Test verification when tests are available** — run the codebase's existing test suite (or the affected module's tests). "Available" means runnable tests exist for the affected code; absence of tests is recorded as `test_verified: not_available`, never silently equated with passing.
- Record both results on the item (`build_verified`, `test_verified`) and in the Execution_Log, then record the checkpoint commit.

### Verification Failure — Report, Block, Log

When an item's build or test verification fails (Requirement 15.21):

1. **Report the failure content** — which verification failed, the error output's substance, and the increment it implicates.
2. **Block subsequent work items.** Do not proceed to the next item in the plan until EITHER the failure is resolved by fixes *within the working branch* (then re-verify and checkpoint), OR the user decides the disposition: **continue** (accept and move on), **skip** (mark this item skipped, proceed), or **abort** (stop plan execution — [interruption handling](#interruption-and-incompletion) takes over).
3. **Record in the Execution_Log** both the failure fact and its disposition (fixed-in-branch / user-continue / user-skip / user-abort), per Requirement 19, before the next action starts.

The fix loop stays inside the working branch and inside the safety rails — a verification failure never justifies touching the source branch, force-pushing, or rewriting the checkpoint history.

### When Local Verification Is Not Possible — Honest Reporting

When the source or the target of a transformation cannot be locally build-verified (Requirement 15.20) — the .NET Framework baseline on a non-Windows host, an absent toolchain, or any other local gap:

1. **Report exactly what could not be verified locally and why** (e.g. "the net48 baseline cannot be built on this Linux host; the ported net8.0 output was built and tested locally").
2. **Present the alternative verification means**, at minimum from: the user's **CI pipeline** building the affected configurations; the **remote build paths of Requirement 16** (e.g. CodeBuild-based image build environments reachable in Migration_Execution); and **verification performed by the user** on a capable host.
3. **Never claim the transformation is verified** when it is not. Unverified is reported as unverified — in the item's result (`build_verified: not_possible`), in the Execution_Log, in the [completion review perspectives](#plan-completion--mandatory-human-review-no-merge), and in conversation. Partial verification (target verified, baseline not) is reported with exactly that granularity.

Record every such gap in `local_verification_gaps` so the completion report and the human review inherit the complete list.

---

## Interruption and Incompletion

When Agent_Executed_Item execution is interrupted, or the plan's work items cannot all be completed (Requirement 15.22):

1. **Report completed vs incomplete items, distinguished** — per item: name, status (`done` with its checkpoint commit / `in_progress` with last checkpoint / `pending` / `skipped` / `verification_failed`), so the user sees precisely where the plan stands.
2. **Preserve the working branch and every checkpoint commit.** Nothing is deleted, reset, or rewritten — the branch and its checkpoints are the user's recovery assets (and Requirement 11.17 forbids destroying them anyway).
3. **Present the options**, at minimum:
   - **Manual continuation by the user** — from the preserved working branch and its last checkpoint;
   - **Scope adjustment** — shrink or reshape the remaining transformation scope (a plan change, handled by the plan-change rules in [code-transformation.md](code-transformation.md#plan-changes), including re-presentation and re-confirmation);
   - **Transform_Augmentation proposal for incomplete items within coverage** — for each unfinished item whose transformation type is inside AWS Transform's documented coverage (per the [two-condition test](code-transformation.md#augmentation-applicability--the-two-condition-test), availability included), propose augmentation per the companion file's proposal rules.
4. **Never claim the transformation is complete.** Partial completion is reported as partial — the same honesty rule as verification.
5. **Log the interruption** — what stopped, item states, and the user's chosen option — in the Execution_Log.

---

## Plan Completion — Mandatory Human Review, No Merge

When ALL work items of the Transformation_Plan are complete (Requirement 15.23) — the agent-executed ones per this file and the Transform-augmented ones per the companion:

1. **Present human code review as a mandatory step before merge.** The transformed result is not merged, deployed, or built upon for release until a human has reviewed it.
2. **Report the review perspectives**, at minimum:
   - **Per-item build and test verification results** — the `build_verified` / `test_verified` outcome of every item, checkpoint commits included;
   - **What could not be verified locally** — the full `local_verification_gaps` list from [the rule above](#when-local-verification-is-not-possible--honest-reporting), with the suggested alternative verification means;
   - **Untransformed parts** — anything the plan did not cover or items that were skipped, plus (for Transform-augmented items) the residual gaps their job reports flagged;
   - **The need for behavioral verification** — functional testing beyond successful builds: green builds and passing unit tests do not establish behavioral equivalence of a port.
3. **Never merge.** The agent does not merge the working branch (or any Transform target branch) into the original source branch — under any circumstances. State explicitly that the merge decision belongs to the user, after their review. This mirrors the companion file's no-merge rule for Transform jobs; the two rules are one policy.
4. **Log the completion report** in the Execution_Log.

---

## Output Schema

Agent_Executed_Item execution fills the agent-side fields of the `code_transformation` block defined in [code-transformation.md](code-transformation.md#output-schema) — this file does not define a second schema. The fields this module owns:

```yaml
# within code_transformation.transformation_plan.items[] (execution: agent):
status: pending | in_progress | done | verification_failed | skipped
build_verified: bool | not_possible     # per-item completion build verification
test_verified: bool | not_available     # tests run when runnable tests exist
checkpoint_commit: string | null        # commit hash recorded at item completion

# within code_transformation:
agent_work_location:
  branch_or_dir: string                  # the user-approved working location
  based_on_transform_target: bool        # true when continuing on a Transform target
                                         # branch / derived branch, user-approved
local_verification_gaps: [string]        # what could not be verified locally, and why
human_review_required: true              # constant — review precedes any merge, always
```

**Reporting invariants (agent side):**

- `status: done` implies a recorded `checkpoint_commit` and a completed verification step (or an explicit `build_verified: not_possible` with its gap recorded).
- `build_verified: true` is never reported without a build actually having run locally; `not_possible` items appear in `local_verification_gaps`.
- `based_on_transform_target: true` is never set without the user's explicit approval of that branch option.
- No item transitions to `in_progress` before the "code transformation start" confirmation covering the current working location.

---

## Edge Cases

### The working location was never explicitly approved

An unapproved location is not a working location. Do not start any item: propose a concrete working branch / directory (and, where Transform target branches exist, the options of Requirement 15.18), obtain approval as part of — or as a re-confirmation of — the "code transformation start" confirmation, and only then begin.

### The user asks the agent to edit the source branch directly "to save time"

Decline and explain the rail: Requirement 11.9 confines code changes to approved non-source locations, and the working-branch model preserves the user's rollback path. Offer the fast alternative that stays inside the rails (work on the approved branch; the user merges after review).

### A work item's target overlaps a Transform target branch the user did not approve for agent work

Operate only in the approved location. If residual work naturally belongs on an unapproved target branch, present the 15.18 options again rather than touching that branch without approval.

### Verification failure whose fix requires changing another item's completed output

Fix forward in the working branch (new commits — never rewrite the earlier checkpoint), re-run the current item's verification, and record both the failure and the forward fix in the Execution_Log. The earlier item's `done` status and checkpoint remain historical facts.

### Tests exist but cannot run locally (missing test infrastructure)

That is a partial local-verification gap: report `build_verified` from the local build, `test_verified: not_available` with the reason, add the gap to `local_verification_gaps`, and present the alternative means (CI, user-run tests) — do not claim test verification.

### The toolchain appears mid-plan (e.g. the user installs the JDK)

Local verifiability is re-determined for pending items; newly verifiable items follow the full verify-and-checkpoint discipline. Completed items are not retroactively re-verified unless the user asks — but the option can be offered.

### An interrupted plan is resumed later

Resume from the preserved working branch and checkpoints, in plan order, starting at the first non-`done` item. If the plan or working location changed in the interim, the re-confirmation rules apply before the first pending item executes.

### Conflicting guidance between this file and live Microsoft/Jakarta documentation

Live documentation wins — the porting tables here are authoring-time knowledge subject to the same freshness posture as the companion's directive. Verify version-specific claims (tool names, supported bindings, removal lists) against the cited sources before presenting them as current.

---

## Sources

- .NET porting overview — Microsoft Learn: https://learn.microsoft.com/en-us/dotnet/core/porting/
- .NET Upgrade Assistant — overview: https://learn.microsoft.com/en-us/dotnet/core/porting/upgrade-assistant-overview
- try-convert (archived; superseded by Upgrade Assistant): https://github.com/dotnet/try-convert
- packages.config → PackageReference migration: https://learn.microsoft.com/en-us/nuget/consume-packages/migrate-packages-config-to-package-reference
- SDK-style vs legacy project formats: https://learn.microsoft.com/en-us/nuget/resources/check-project-format
- ASP.NET to ASP.NET Core migration (MVC, Web API, configuration, Global.asax): https://learn.microsoft.com/en-us/aspnet/core/migration/proper-to-2x/
- ASP.NET incremental migration (YARP + System.Web adapters): https://learn.microsoft.com/en-us/aspnet/core/migration/inc/overview
- ASP.NET Core configuration (appsettings.json, options pattern): https://learn.microsoft.com/en-us/aspnet/core/fundamentals/configuration/
- Kestrel web server: https://learn.microsoft.com/en-us/aspnet/core/fundamentals/servers/kestrel
- Windows Compatibility Pack: https://learn.microsoft.com/en-us/dotnet/core/porting/windows-compat-pack
- .NET Framework technologies unavailable on modern .NET: https://learn.microsoft.com/en-us/dotnet/core/porting/net-framework-tech-unavailable
- Platform Compatibility Analyzer (CA1416): https://learn.microsoft.com/en-us/dotnet/standard/analyzers/platform-compat-analyzer
- CoreWCF (WCF service hosting on modern .NET): https://github.com/CoreWCF/CoreWCF
- Worker Services in .NET (Windows Service replacement): https://learn.microsoft.com/en-us/dotnet/core/extensions/workers
- System.Drawing.Common Linux support removal: https://learn.microsoft.com/en-us/dotnet/core/compatibility/core-libraries/6.0/system-drawing-common-windows-only
- Jakarta EE 9 — javax → jakarta namespace: https://jakarta.ee/specifications/platform/9/
- Eclipse Transformer (automated javax → jakarta rewriting): https://projects.eclipse.org/projects/technology.transformer
- OpenRewrite migration recipes (Jakarta, Spring Boot 3, JDK upgrades): https://docs.openrewrite.org/recipes/java/migrate
- Apache Tomcat migration tool for Jakarta EE: https://tomcat.apache.org/download-migration.cgi
- Spring Boot 3.0 migration guide (Java 17 floor, jakarta namespace): https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide
- Oracle JDK 17 migration guide (removals, encapsulation, Java EE module removal): https://docs.oracle.com/en/java/javase/17/migrate/
- Maven compiler plugin (`release` option): https://maven.apache.org/plugins/maven-compiler-plugin/
- Maven surefire plugin (JDK compatibility): https://maven.apache.org/surefire/maven-surefire-plugin/
- Gradle compatibility matrix (Gradle version × JDK): https://docs.gradle.org/current/userguide/compatibility.html

The transformation process model, augmentation determination, evidence comparison, and Transform-augmented execution knowledge live in the companion file, [code-transformation.md](code-transformation.md); its Technical Freshness Directive's posture — verify against live sources before relying on version-specific claims — applies to the porting knowledge in this file as well.
