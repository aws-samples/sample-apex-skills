---
title: "Module: Tech Stack Detection"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-modernize/references/tech-stack-detection.md
format: md
---

:::info[Source]
This page is generated from [skills/ecs-modernize/references/tech-stack-detection.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-modernize/references/tech-stack-detection.md). Edit the source, not this page.
:::

# Module: Tech Stack Detection

> **Part of:** [ecs-modernize](../)
> **Purpose:** Identify the languages, frameworks, runtimes, declared versions, and application servers of the target application from source code — the evidence base every downstream analysis module builds on
> **Prerequisites:** None (first module in the analysis pipeline)

This module is deliberately orchestrator-neutral: it describes what the application **is**, not where it should run. It contains no target-platform vocabulary — strategy and target-platform knowledge live in the path modules. This file covers tech stack detection only; blocker detection, scoring, and strategy recommendation are each defined in their own reference file.

## Table of Contents

- [Inputs](#inputs)
- [Detection and Classification Procedure](#detection-and-classification-procedure)
- [Classification Criteria](#classification-criteria)
  - [1. Language Detection and Classification](#1-language-detection-and-classification)
  - [2. Primary Language Selection](#2-primary-language-selection)
  - [3. Java Framework Classification](#3-java-framework-classification)
  - [4. .NET Runtime Classification](#4-net-runtime-classification)
  - [5. .NET Application Framework Classification](#5-net-application-framework-classification)
  - [6. Language and Runtime Version Declarations](#6-language-and-runtime-version-declarations)
  - [7. Application Server Detection](#7-application-server-detection)
- [Output Schema](#output-schema)
- [Edge Cases](#edge-cases)

---

## Inputs

- **Source code root path** (required) — the directory tree to analyze, provided by the user.
- **Read-only discipline** — this module runs during the assessment phase and performs static analysis only:
  - Read file contents only. Never create, modify, delete, move, or rename anything under the source path.
  - Never execute build, dependency-resolution, test, or packaging commands (`mvn`, `gradle`, `dotnet`, `msbuild`, `nuget`, `npm install`, `pip install`, ...), regardless of where their output would land.
- **No prerequisite modules** — the output of this module feeds blocker detection and scoring.

---

## Detection and Classification Procedure

Run the steps in this order:

```
0. Validate the source path        -> hard stop if missing or unreadable
1. Inventory build definitions     -> strongest single evidence source
2. Map source file extension distribution
3. Classify languages; select the primary language when several are present
4. Detect frameworks per detected language (Java branch / .NET branch)
5. Extract declared language and runtime versions from build definitions
6. Scan for application server deployment descriptors (always, independent of language)
7. Assemble the output: evidence attached to every determined item,
   undetermined items recorded with what was considered and what is missing
```

**Why this order:**

- Step 0 gates everything. If the source path itself does not exist or cannot be read, there is nothing to analyze and no downstream module (blocker detection, scoring, recommendation) may run — see [Edge Cases](#source-path-missing-or-unreadable--abort).
- Build definitions (step 1) anchor three findings at once — language, declared versions, and framework dependencies — so read them before scanning individual source files.
- Extension distribution (step 2) covers repositories where build definitions are absent or incomplete, and provides the composition ratio used to select the primary language.
- Framework detection (step 4) depends on the language classification from step 3, so it comes after.
- The application server scan (step 6) runs unconditionally: deployment descriptors are reported even when they do not match the detected language — a `weblogic.xml` in a repository classified as .NET is still a finding worth surfacing.

### Step 0 — Validate the source path

Confirm the given path exists and is readable (directory listing succeeds). On failure, stop: report the error naming the exact path, and do not proceed (see Edge Cases).

### Step 1 — Inventory build definitions

Glob the tree for build and dependency definitions, recording the path of each hit:

| Ecosystem | Files |
|---|---|
| Maven | `pom.xml` |
| Gradle | `build.gradle`, `build.gradle.kts`, `settings.gradle`, `settings.gradle.kts` |
| MSBuild / .NET | `*.csproj`, `*.vbproj`, `*.sln`, `packages.config`, `Directory.Build.props` |
| Node.js | `package.json` |
| Python | `pyproject.toml`, `requirements.txt`, `setup.py` |
| Go | `go.mod` |
| Ruby | `Gemfile` |
| PHP | `composer.json` |

Also capture the **application name** when declared (Maven `<name>` or `<artifactId>`, `.sln` solution name, `package.json` `name`); the report module uses it for the default report file name. If none is declared, leave it null (the report module falls back to the source root directory name).

### Step 2 — Map extension distribution

Count source files per language, **excluding** vendored and generated directories: `node_modules/`, `target/`, `build/`, `out/`, `bin/`, `obj/`, `dist/`, `.git/`, `packages/`, `vendor/`, `.venv/`. The composition ratio (files of language X ÷ total counted source files) is evidence for primary-language selection.

### Steps 3–6

Apply the [Classification Criteria](#classification-criteria) below.

### Step 7 — Assemble the output

Fill the [Output Schema](#output-schema). Two reporting rules apply to every item:

1. **Every determined item carries at least one evidence entry** `{path, detail}` where `detail` quotes or precisely describes the matching content. This holds regardless of whether *other* items ended up undetermined — never drop evidence from successful determinations just because the analysis is partially incomplete.
2. **Every undetermined item is recorded explicitly** with the evidence that was considered and the information that is missing. Never guess a value to avoid reporting `undetermined`.

---

## Classification Criteria

### 1. Language Detection and Classification

Report **all** detected programming languages, and classify each into exactly one of:

| Classification | Trigger evidence |
|---|---|
| `java` | `pom.xml` / `build.gradle(.kts)` present, and/or `*.java` sources |
| `dotnet` — C# (.NET) | `*.csproj` / `*.sln` / `packages.config` present, and/or `*.cs` sources |
| `other` — record the language name | Any other language: e.g. `package.json` + `*.js`/`*.ts` (JavaScript/TypeScript), `pyproject.toml`/`requirements.txt` + `*.py` (Python), `go.mod` + `*.go` (Go), `Gemfile` + `*.rb` (Ruby), `composer.json` + `*.php` (PHP) |

A language counts as detected when **either** a build definition **or** source files for it exist; having both strengthens the evidence. Report each language with its evidence (build definition paths, representative source paths, file counts).

### 2. Primary Language Selection

When more than one language is detected, select the **primary language** — the one that downstream framework detection and scoring will focus on — and report the selection **with its rationale**. Weigh, in order:

1. **Build definition presence and position** — a language with a build definition at or near the repository root outweighs a language present only as source files (e.g. a Java service with a `pom.xml` at root plus a `webapp/` folder of JavaScript assets → Java is primary).
2. **Source file composition ratio** — from step 2, excluding vendored/generated directories.
3. **Entry-point evidence** — where the deployable artifact is defined (e.g. the module producing a `war`/executable vs. supporting scripts).

The rationale in the output must name the evidence actually used (which build definitions exist, the observed composition ratio). If the evidence is contradictory or too thin to choose (see Edge Cases), record the primary language as an undetermined item rather than guessing.

A single detected language is trivially primary; `rationale` may be null in that case.

### 3. Java Framework Classification

When Java is detected, report **all** detected frameworks using at least these classifications. Multiple frameworks in one codebase are all reported — coexistence is common in long-lived applications and downstream scoring handles the ranking; this module only collects the facts.

| Framework | Evidence patterns |
|---|---|
| **Spring Boot** | `spring-boot-starter*` dependencies in `pom.xml` / Gradle files; `spring-boot-maven-plugin` / `org.springframework.boot` Gradle plugin; `@SpringBootApplication` in sources; `application.properties` / `application.yml` with Spring Boot keys |
| **Spring Framework (non-Boot)** | `spring-context`, `spring-webmvc`, `spring-core` dependencies **without any** `spring-boot-*` artifact; XML application contexts (`applicationContext.xml`, `*-servlet.xml`); `@Controller`/`@Service` without Boot starters |
| **Struts** | `struts.xml` (Struts 2), `struts-config.xml` (Struts 1); `struts2-core` / `struts-core` dependencies; `org.apache.struts` imports |
| **Jakarta EE / Java EE** | `javax.*` / `jakarta.*` platform API imports (`javax.ejb`, `javax.servlet`, `jakarta.servlet`, ...); `application.xml`, `ejb-jar.xml`; provided-scope `javaee-api` / `jakarta.jakartaee-api` dependencies |

Disambiguation: the presence of **any** `spring-boot-*` artifact classifies the Spring usage as Spring Boot; classify as Spring Framework (non-Boot) only when Spring dependencies exist with no Boot artifact anywhere in the build definitions.

If **no** framework is detected for a Java codebase, report exactly: **no framework (plain Java)** — this is a positive finding, not an omission.

### 4. .NET Runtime Classification

When C# (.NET) is detected, classify the runtime of **each project** (each `.csproj`) into one of:

| Classification | Evidence patterns |
|---|---|
| **.NET Framework (4.x and earlier)** → `dotnet_framework` | SDK-style `<TargetFramework>` of `net48`, `net472`, `net462`, `net40`, `net35`, ...; legacy-style `<TargetFrameworkVersion>v4.x</TargetFrameworkVersion>`; `packages.config` presence (legacy project format signal) |
| **.NET (Core / 5 and later)** → `dotnet_modern` | `<TargetFramework>` of `netcoreapp2.x` / `netcoreapp3.1`, `net5.0`, `net6.0`, `net8.0`, `net10.0`, ... |

Rules:

- **Multi-target projects** (`<TargetFrameworks>net48;net8.0</TargetFrameworks>`) → report **both** runtimes for that project. Do not collapse to one.
- **Multiple projects with mixed runtimes** (e.g. a `.sln` containing one `net48` project and one `net8.0` project) → report **every** project's runtime with its `.csproj` path as evidence. The mix itself is a finding downstream modules need.
- `netstandard*` targets identify libraries, not runtimes — see Edge Cases.

### 5. .NET Application Framework Classification

When C# (.NET) is detected, report the detected application frameworks, including at least these classification targets (report any additional framework found by name):

| Framework | Evidence patterns |
|---|---|
| **ASP.NET Web Forms** | `.aspx` / `.ascx` / `.master` files; `System.Web` references with code-behind (`.aspx.cs`) |
| **ASP.NET MVC** | `System.Web.Mvc` assembly/package reference; `Controllers/` + Razor `.cshtml` under a legacy-style project |
| **WCF** | `System.ServiceModel` references; `.svc` files; `<system.serviceModel>` sections in `web.config` / `app.config` |
| **ASP.NET Core** | `Microsoft.AspNetCore.*` package references; minimal-hosting `Program.cs` (`WebApplication.CreateBuilder`) |

Multiple frameworks (e.g. Web Forms pages alongside MVC controllers in one project) are all reported, each with its own evidence.

### 6. Language and Runtime Version Declarations

Wherever a build definition **declares** a language or runtime version, report the declared version **together with the file path of the declaring build definition**:

| Ecosystem | Declaration keys |
|---|---|
| Maven | `maven.compiler.source` / `maven.compiler.target` / `maven.compiler.release`, `<java.version>` property |
| Gradle | `sourceCompatibility` / `targetCompatibility`, `java.toolchain.languageVersion` |
| MSBuild | `<TargetFramework>` / `<TargetFrameworks>`, `<TargetFrameworkVersion>`, `<LangVersion>` |
| Node.js | `package.json` → `engines.node` |
| Python | `pyproject.toml` → `requires-python`, `.python-version` |
| Go | `go.mod` → `go` directive |

Report only what is declared — an absent declaration is not a version of "unknown-but-probably-X"; it makes the version `undetermined` for that item (record what was checked). For each runtime, also record whether the detected version has reached its provider's published end of support (`eol: true | false | undetermined`) by checking the vendor's support lifecycle for that version at analysis time; if the version itself is undetermined, `eol` is `undetermined` too. Interpretation of EOL status (legacy classification, score impact) belongs to the scoring module, not here.

### 7. Application Server Detection

Scan for application server deployment configuration **unconditionally** and report **every** server found — regardless of whether it is consistent with the detected language — each with the path(s) of the configuration file(s) that evidence it:

| Server / deployment target | Evidence patterns |
|---|---|
| Servlet container deployment (server not yet identified) | `WEB-INF/web.xml` |
| Oracle WebLogic | `weblogic.xml`, `weblogic-application.xml` |
| IBM WebSphere Application Server **traditional** (tWAS) | `ibm-web-bnd.xml` / `ibm-web-ext.xml`, `ibm-ejb-jar-bnd.xml` / `ibm-ejb-jar-ext.xml`, `ibm-application-bnd.xml`, `deployment.xml`, `was.policy`; wsadmin administration scripts (`*.jacl`, or Jython scripts invoking `AdminApp` / `AdminConfig` / `AdminTask`) |
| IBM WebSphere **Liberty** / Open Liberty | Liberty `server.xml` (root element `<server>` containing `<featureManager>`), `server.env`, `jvm.options`, `bootstrap.properties`; `liberty-maven-plugin` / `liberty-gradle-plugin` in build definitions |
| Apache Tomcat | Tomcat `server.xml` (root element `<Server>` with Catalina `<Service>`/`<Connector>` elements), `context.xml`, `catalina.properties` |
| JBoss / WildFly | `jboss-web.xml`, `standalone.xml` |
| Microsoft IIS | `web.config` containing `<system.webServer>`, `applicationHost.config` |

A `web.xml` alone establishes servlet-container deployment without identifying the vendor; report it as such unless a vendor-specific descriptor pins the server. When a detected server does not match the detected language (e.g. `weblogic.xml` in a repository classified as .NET), still report it and note the inconsistency — it often signals a multi-application repository or leftover configuration, either of which downstream modules should know about.

**`server.xml` name collision (Tomcat vs Liberty).** Both servers use a file named `server.xml`; never classify on the file name alone. Distinguish by content: a Liberty `server.xml` has the root element `<server>` and typically a `<featureManager>` with `<feature>` entries; a Tomcat `server.xml` has the root element `<Server>` with Catalina `<Service>` / `<Connector>` children. If the file is unreadable or its content matches neither shape, report the server as an undetermined item with the file path as the considered evidence.

**Proprietary server-API coupling scan.** When a vendor application server is detected — or independently, when Java sources import vendor server APIs — scan the sources for proprietary API usage and attach the findings to the server's evidence entries, because the *depth* of server coupling (deployment descriptors only vs. code-level API dependence) matters to downstream scoring and path selection:

| Vendor | Proprietary API evidence patterns |
|---|---|
| IBM WebSphere | `com.ibm.websphere.*` / `com.ibm.wsspi.*` / `com.ibm.ejs.*` imports; CommonJ `commonj.work` / `commonj.timers` (WorkManager / TimerManager); WAS-specific JNDI lookups in code or descriptors |
| Oracle WebLogic | `weblogic.*` imports (e.g. `weblogic.jndi`, `weblogic.transaction`); WebLogic-specific work managers |

Report each finding as evidence `{path, detail}` under the corresponding `app_servers` entry. Code-level API usage found with **no** matching server descriptor is still reported (leftover coupling from a previous host is a finding, not noise).

---

## Output Schema

This module produces the `analysis` envelope (target identity and partial-analysis state) and the `tech_stack` block. Hold the structure in conversation context — the assessment phase writes no intermediate files.

```yaml
analysis:
  target:
    source_path: string            # analyzed root
    app_name: string | null        # from build definitions; null -> report module falls back to root dir name
  partial: bool                    # true when any path was excluded as unreadable
  excluded_paths:                  # unreadable ranges excluded from analysis
    - {path: string, reason: string}

tech_stack:
  languages:
    - name: string                 # e.g. "Java", "C#", "Python"
      classification: java | dotnet | other   # for `other`, name carries the language name
      primary: bool                # exactly one true when any language is determinable
      rationale: string | null     # primary-selection grounds; required when multiple languages detected
  frameworks:
    - name: string                 # e.g. "Spring Boot", "Struts", "ASP.NET Web Forms",
                                   #      "no framework (plain Java)"
      classification: string       # framework family name; the scoring module maps families
                                   # onto its modernity ladder (single source of truth there)
      evidence: [{path: string, detail: string}]   # >= 1 entry per determined item
  runtimes:
    - name: string                 # e.g. ".NET Framework 4.8", "Java 8"
      classification: dotnet_framework | dotnet_modern | jvm | other
      version: string | undetermined
      eol: bool | undetermined     # provider support ended at analysis time?
      evidence: [{path: string, detail: string}]   # declaring build definition path + declaration
  app_servers:
    - {name: string, evidence: [{path: string, detail: string}]}
  undetermined_items:
    - item: string                 # e.g. "primary language", "runtime version of project X"
      considered_evidence: string  # what was examined
      missing_info: string         # what would settle the determination
```

**Reporting invariants:**

- Every `frameworks`, `runtimes`, and `app_servers` entry — and every language detection — carries at least one `evidence` entry. Evidence stays attached even when other items are `undetermined`.
- Multi-target and mixed-project runtimes appear as multiple `runtimes` entries (or multiple evidence entries under one runtime name), never collapsed.
- `undetermined_items` is the only legitimate destination for anything that could not be settled from the available evidence.

---

## Edge Cases

### Source path missing or unreadable — abort

If the given source path does not exist or cannot be read at all:

- **Stop the analysis.** Report an error that names the inaccessible path explicitly.
- **Do not run any downstream module** — no blocker detection, no scoring, no strategy recommendation, no report claiming analysis results.
- Do not substitute a guessed or "nearby" path without the user confirming it.

### Some files unreadable — continue with exclusions

If the source path itself is accessible but individual files or subdirectories cannot be read:

- **Continue the analysis** over everything readable.
- Record each excluded path (or directory range) with its reason in `analysis.excluded_paths`, and set `analysis.partial: true`.
- Downstream modules and the report treat the results as a partial analysis (the report includes an incomplete-analysis section); this module's job is to hand over an accurate exclusion list, not to hide it.

### Item cannot be determined

When a determination target (language, framework, runtime, language/runtime version) cannot be settled from the available evidence, record it in `undetermined_items` with the evidence considered and the missing information. Examples:

- No build definition and ambiguous extensions → language `undetermined`; considered: extension scan results; missing: a build definition or representative sources.
- `.csproj` unreadable → runtime of that project `undetermined`; considered: project file path (unreadable); missing: its `TargetFramework` value.
- No version declaration anywhere → version `undetermined`; considered: the build definitions inspected; missing: a version declaration key.

### Ambiguous primary language

If multiple languages tie on both build-definition presence and composition ratio (e.g. a true polyglot monorepo), do not pick arbitrarily: record the primary language as undetermined, list the candidates with their evidence, and ask the user which application is the migration target. Framework detection may still proceed per detected language.

### `netstandard` targets

`netstandard*` identifies a library compatibility surface, not a runtime. Report such projects as evidence, but derive the runtime from the **consuming application project**. If only `netstandard` projects exist (a pure library repository), the runtime is `undetermined` — note that an application entry point is missing.

### Build definitions and sources disagree

- A build definition with no matching sources (e.g. `pom.xml` but zero `.java` files): report the language with the build definition as evidence and note the absence of sources — possibly an aggregator/parent module.
- Sources with no build definition: report the language from extension evidence, and expect versions to come out `undetermined` (no declaration to cite).

### Conflicting or coexisting framework signals

Multiple framework signals (e.g. `spring-boot-starter-web` **and** `struts.xml` in one tree) are not a conflict to resolve here — report **all** of them, each with its own evidence. Ranking coexisting frameworks is the scoring module's job.

---

## Sources

- .NET target framework monikers (`net4x`, `netcoreapp*`, `net5.0`+, `netstandard*`): https://learn.microsoft.com/en-us/dotnet/standard/frameworks
- .NET and .NET Framework support lifecycles (EOL checks): https://learn.microsoft.com/en-us/lifecycle/products/
- Java SE support roadmap (EOL checks): https://www.oracle.com/java/technologies/java-se-support-roadmap.html
- Maven compiler properties (`maven.compiler.source/target/release`): https://maven.apache.org/plugins/maven-compiler-plugin/
- Gradle Java toolchains (`languageVersion`): https://docs.gradle.org/current/userguide/toolchains.html
- WebSphere binding/extension deployment descriptors (`ibm-web-bnd.xml` and family): https://www.ibm.com/docs/en/radfws/9.7.0?topic=descriptors-generating-websphere-extensions-bindings-deployment
- Liberty `server.xml` configuration (root `<server>`, `featureManager`): https://openliberty.io/docs/latest/reference/config/server-configuration-overview.html
- Apache Tomcat `server.xml` reference (Catalina `<Server>`/`<Service>`): https://tomcat.apache.org/tomcat-10.1-doc/config/server.html
