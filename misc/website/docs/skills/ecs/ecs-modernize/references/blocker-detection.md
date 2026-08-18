---
title: "Module: Blocker Detection"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-modernize/references/blocker-detection.md
format: md
---

:::info[Source]
This page is generated from [skills/ecs-modernize/references/blocker-detection.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-modernize/references/blocker-detection.md). Edit the source, not this page.
:::

# Module: Blocker Detection

> **Part of:** [ecs-modernize](../)
> **Purpose:** Detect the concrete findings in the source code that obstruct containerization or cloud migration, classify each into a blocker category, and assign every blocker exactly one remediation class (tolerated under Replatform vs. must-fix even for Replatform)
> **Prerequisites:** Tech Stack Detection ([tech-stack-detection.md](tech-stack-detection)) — the evidence patterns below are selected by detected language and framework

This module is deliberately orchestrator-neutral: it describes what prevents the application from running in a container or moving to the cloud, not where it should run. Strategy-level vocabulary (Replatform / Rearchitect) appears here only because the remediation classes are defined against those two strategies; target-platform vocabulary does not appear at all — it lives in the path modules. This file covers blocker detection only; tech stack detection, scoring, and strategy recommendation are each defined in their own reference file.

## Table of Contents

- [Inputs](#inputs)
- [Detection and Classification Procedure](#detection-and-classification-procedure)
- [Classification Criteria](#classification-criteria)
  - [The Six Blocker Categories](#the-six-blocker-categories)
    - [1. Local Filesystem State Writes (`local_state`)](#1-local-filesystem-state-writes-local_state)
    - [2. In-Process Session State (`in_process_session`)](#2-in-process-session-state-in_process_session)
    - [3. Hardcoded Connection Info and Credentials (`hardcoded_credentials`)](#3-hardcoded-connection-info-and-credentials-hardcoded_credentials)
    - [4. OS-Specific API Dependencies (`os_specific_api`)](#4-os-specific-api-dependencies-os_specific_api)
    - [5. Container-Incompatible Process Model (`process_model`)](#5-container-incompatible-process-model-process_model)
    - [6. Licensing Constraints (`licensing`)](#6-licensing-constraints-licensing)
  - [The `other` Category](#the-other-category)
  - [Remediation Class Assignment](#remediation-class-assignment)
- [Reporting Rules](#reporting-rules)
- [Output Schema](#output-schema)
- [Edge Cases](#edge-cases)

---

## Inputs

- **Source code root path** (required) — the same tree analyzed by tech stack detection.
- **`tech_stack` block and `analysis` envelope** (required) — the output of the tech stack detection module. Detection here is language- and framework-directed: the evidence patterns to apply are chosen from the detected languages (Java branch, .NET branch, other), frameworks, and application servers. Do not run this module before tech stack detection has produced its output.
- **Read-only discipline** — this module runs during the assessment phase and performs static analysis only:
  - Read file contents only. Never create, modify, delete, move, or rename anything under the source path.
  - Never execute build, dependency-resolution, test, or packaging commands, regardless of where their output would land.

---

## Detection and Classification Procedure

Run the steps in this order:

```
1. Select evidence patterns          -> driven by the detected languages/frameworks
2. Scan configuration artifacts      -> deployment descriptors, app config, license files
3. Scan source code per category     -> the six categories below, in any order
4. Record non-category obstructions  -> anything blocking that fits no category -> `other`
5. Assign remediation class          -> exactly one of two classes per blocker
6. Apply credential secrecy rules    -> before anything is written to output
7. Assemble the output               -> including the explicit zero-blocker statement
                                        and partial-analysis exclusions when applicable
```

**Why this order:**

- Pattern selection (step 1) comes first because the categories share names but not evidence: "OS-specific API dependency" means registry and COM lookups in a .NET codebase, but JNI and native-library loading in a Java codebase. Scanning with the wrong ecosystem's patterns produces both misses and noise.
- Configuration artifacts (step 2) are scanned before sources because they are small, high-signal files: a single `web.config` line settles the session-state mode for the whole application, and a license file settles the licensing category for a component regardless of how many sources use it.
- Class assignment (step 5) runs after all findings are collected, because some class decisions need the full picture — e.g. whether every native dependency of a P/Invoke finding can be shipped inside a container image.
- Credential secrecy (step 6) is applied before output assembly so that no intermediate representation carried into the report can leak a value.

### Step 1 — Select evidence patterns

From `tech_stack.languages` / `frameworks` / `app_servers`, choose the applicable rows of each category table below. Patterns for undetected ecosystems may be skipped; patterns marked *any ecosystem* always apply. If the primary language is undetermined, apply the patterns of **every** detected language rather than skipping detection.

### Step 2 — Scan configuration artifacts

Deployment descriptors (`web.xml`, `web.config`, `app.config`, server-specific descriptors), application configuration (`*.properties`, `*.yml`, `appsettings*.json`, `.env`), startup/service scripts, and license/README files. Record each hit with its path.

### Steps 3–5

Apply the [Classification Criteria](#classification-criteria) below. Every finding becomes a blocker entry with a category (step 3–4) and exactly one remediation class (step 5).

### Step 6 — Apply credential secrecy rules

For every blocker in the `hardcoded_credentials` category (and any other blocker whose evidence involves a credential), enforce the [secrecy rules](#credential-value-secrecy) before the finding is expressed anywhere.

### Step 7 — Assemble the output

Fill the [Output Schema](#output-schema). Three reporting rules always apply — per-blocker completeness, the explicit zero-blocker statement, and partial-analysis disclosure — see [Reporting Rules](#reporting-rules).

---

## Classification Criteria

### The Six Blocker Categories

Each category defines the evidence patterns that justify a detection. A finding is a blocker only when it obstructs containerization or cloud migration; the `reason` field of every blocker must state **why** it obstructs (what breaks, or what property of containers/cloud it violates).

#### 1. Local Filesystem State Writes (`local_state`)

The application persists **state** — business data whose loss on process replacement harms the application — to the local filesystem. Pure log output to local files is *not* this blocker (log redirection is a routine containerization task); the target is data persistence other than logs.

| Ecosystem | Evidence patterns |
|---|---|
| Java | `FileWriter` / `FileOutputStream` / `Files.write` / `RandomAccessFile` targeting fixed local paths; file-backed embedded databases (H2 / HSQLDB / Derby / SQLite file URLs in JDBC config); file-based caches or queues; upload/data directories declared in `*.properties` / `*.yml` |
| .NET | `File.WriteAllText` / `StreamWriter` / `FileStream` with create/append modes targeting fixed paths; `Server.MapPath(...)` combined with writes; persistent use of `App_Data`; file-backed data stores configured in `web.config` / `appsettings*.json` |
| Any ecosystem | Configuration keys naming writable data directories (`upload.dir`, `data.path`, `storage.root`, ...); documentation or scripts that provision local data directories the application requires |

**Why it obstructs:** container filesystems are ephemeral — state written locally is lost when the instance is replaced, and is invisible to horizontally scaled replicas.

#### 2. In-Process Session State (`in_process_session`)

User session state is held in the application process's memory as the authoritative copy.

| Ecosystem | Evidence patterns |
|---|---|
| Java | `HttpSession.setAttribute(...)` storing business objects; absence of `<distributable/>` in `web.xml` for a session-using servlet application; no external session store dependency (e.g. Spring Session with an external backend) anywhere in the build definitions. **WebSphere traditional caveat:** on tWAS, session persistence (database persistence and DRS memory-to-memory replication, both documented on the 8.5.5 and 9.0 lines) is configured in the server cell configuration, which usually lives outside the application source tree — when the app evidences session usage and the tree carries no session-persistence evidence either way, report the blocker with a note that server-side session persistence may exist and needs user confirmation |
| .NET | `web.config` `<sessionState mode="InProc">`, or a `<sessionState>` element with no `mode` attribute (InProc is the default), or session usage (`Session[...]` in code-behind/controllers) with no `<sessionState>` element at all; no external session provider configured |
| Any ecosystem | Static / singleton in-memory maps keyed by user or session identifiers holding authoritative state |

**Why it obstructs:** with more than one replica — or across any instance replacement — requests lose their session unless traffic is pinned to a single process; in-memory session defeats horizontal scaling and zero-downtime replacement.

#### 3. Hardcoded Connection Info and Credentials (`hardcoded_credentials`)

Connection endpoints and/or secrets are embedded in source or configuration committed with the source.

| Ecosystem | Evidence patterns |
|---|---|
| Java | Connection-string literals in source (`jdbc:...` with embedded host/user/password); credential keys in `*.properties` / `*.yml` (`password`, `passwd`, `pwd`, `secret`, `apiKey`, `token`, ...) with non-placeholder values; keystore files plus their passwords in config |
| .NET | `<connectionStrings>` in `web.config` / `app.config` with `Password=` / `User ID=` components; credential keys in `appsettings*.json`; secrets in `<appSettings>` values |
| Any ecosystem | URL userinfo credentials (`scheme://user:pass@host`); high-entropy string literals assigned to secret-suggesting identifiers; private keys or `.env` files with real values committed to the tree |

**Why it obstructs:** environment-specific endpoints and secrets baked into the artifact prevent the same build from moving across environments, and committed secrets are a security liability that cloud migration surfaces (image layers, repositories, and logs all become distribution channels).

**Secrecy rules apply** — see [Credential value secrecy](#credential-value-secrecy). The detected **values** never appear in any output of this module, in whole or in part.

#### 4. OS-Specific API Dependencies (`os_specific_api`)

The application calls operating-system-specific interfaces.

| Ecosystem | Evidence patterns |
|---|---|
| .NET | `Microsoft.Win32.Registry` / `RegistryKey` usage; Windows service plumbing (`System.ServiceProcess.ServiceBase`); COM interop (`[ComImport]`, `Marshal.GetActiveObject`, `dynamic` COM activation); P/Invoke (`[DllImport(...)]`) into Windows DLLs; `System.Messaging` (MSMQ); `System.DirectoryServices`; Windows Event Log APIs; desktop UI frameworks (WinForms / WPF references) |
| Java | JNI (`System.loadLibrary` / `System.load`) with platform-specific native libraries; JNA bindings to OS APIs; `Runtime.exec` / `ProcessBuilder` invoking OS-specific commands; hardcoded OS-specific paths (`C:\...`, backslash path building) |
| Any ecosystem | Native modules or extensions compiled per-OS; direct device or driver access; dependencies documented as requiring a specific host OS feature |

**Why it obstructs:** these APIs bind the application to a specific host OS and, in the worst cases, to capabilities (interactive desktop sessions, hardware drivers, kernel-mode components) that no container provides. The remediation class depends on whether the API functions inside a container of the matching OS — see [Remediation Class Assignment](#remediation-class-assignment).

#### 5. Container-Incompatible Process Model (`process_model`)

The deployment unit expects a process model a single container does not provide.

| Ecosystem | Evidence patterns |
|---|---|
| Any ecosystem | Startup scripts launching multiple cooperating long-running processes; dependence on host init/service managers (systemd units, `init.d` scripts, multiple registered OS services) for lifecycle management; required scheduled jobs registered with the host scheduler (cron entries, task scheduler definitions) outside the application process; components communicating through host-local IPC with separately managed processes; logic assuming the host survives application restarts (state in OS services, host reboot hooks) |

**Why it obstructs:** a container packages one isolated process tree with its own lifecycle; applications that rely on the host to supervise several processes, schedule jobs, or persist daemon state cannot be lifted into a single image without reproducing that supervision.

#### 6. Licensing Constraints (`licensing`)

A commercial component's license restricts execution in containers or virtualized/cloud environments.

| Ecosystem | Evidence patterns |
|---|---|
| Any ecosystem | License files, `THIRD-PARTY` notices, or vendor documentation in the tree naming restrictions on container/virtualized execution; per-socket / per-physical-core licensing terms; license activation bound to hardware fingerprints, MAC addresses, or dongles; named-host licenses tied to specific machine identities |
| Java (commercial application server) | A commercial application server detected by tech stack detection (e.g. IBM WebSphere traditional, Oracle WebLogic) whose runtime must ship **inside** the container image. Container execution is typically *permitted* for entitled customers (IBM publishes ILAN-licensed tWAS container images for entitled use), so the finding is usually `replatform_ok` — but the entitlement and the container licensing metric (e.g. per-VPC/PVU counting inside containers) must be confirmed by the user; record that confirmation need in the reason |

**Why it obstructs:** hardware-bound activation fails outright inside containers (also a technical blocker), and prohibitive or physical-hardware-metric license terms make container execution non-compliant or economically unviable. For commercial application servers, the obstruction is compliance-and-cost shaped: the server's license travels into every container image that bundles it, so entitlement coverage and metric counting must be settled before the path is viable.

### The `other` Category

If a detected item obstructs containerization or cloud migration but fits **none** of the six categories, classify it as `other` and record, in `category_rationale`, the grounds for judging it an obstruction (what breaks in a container or in the cloud, and the evidence for that judgment). Never force-fit a finding into a wrong category, and never drop an obstruction because no category matches. `other` blockers follow every reporting rule that applies to the six categories, including remediation class assignment.

### Remediation Class Assignment

Every blocker receives **exactly one** of two remediation classes — never both, never neither:

| Class | Meaning |
|---|---|
| `replatform_ok` | Tolerated under Replatform (the unchanged application still runs in a container), but requires remediation under Rearchitect |
| `must_fix` | Must be resolved even for Replatform — the item cannot operate inside a container |

**Decision test.** Ask: *would the unchanged application operate correctly inside a container, given only the non-code remediations available to a Replatform — external storage volumes mounted at write targets, load-balancer session affinity, configuration files imported into the image or environment, and required user-mode libraries installed at image build time?*

- **Yes** → `replatform_ok`
- **No** → `must_fix`
- **Cannot be determined from the available evidence** → `must_fix` **with `class_unconfirmed: true`** — fail safe, and attach a note that the class is not confirmed by evidence (see Edge Cases)

**Typical class by category** (the decision test always governs; these are the expected outcomes):

| Category | Typical class | Grounds |
|---|---|---|
| `local_state` | `replatform_ok` | An external storage volume mounted at the write target lets the unchanged application run; Rearchitect externalizes the state itself |
| `in_process_session` | `replatform_ok` | Load-balancer session affinity tolerates it without code change (sessions on a replaced instance are still lost — the path module owns presenting that constraint); Rearchitect externalizes the session store |
| `hardcoded_credentials` | `replatform_ok` | The application runs in a container as-is; the embedded values remain a security and portability liability that Rearchitect resolves by externalizing configuration and secrets |
| `os_specific_api` | Depends | `replatform_ok` when the API functions inside a container of the matching OS — registry access, in-process COM, user-mode P/Invoke or JNI whose native libraries can be shipped in the image, service plumbing adaptable to a foreground process. `must_fix` when no container provides the capability: interactive desktop UI sessions, hardware drivers, kernel-mode components, out-of-process dependencies that cannot be installed into an image |
| `process_model` | Depends | `replatform_ok` when the entire process tree can be reproduced inside one image (a supervisor launching the same processes, an in-container scheduler). `must_fix` when correctness depends on host-level init/daemon management, host reboot semantics, or cooperating OS services that cannot be co-located in one container |
| `licensing` | Depends | `must_fix` when terms prohibit container/virtualized execution or activation is hardware-bound. `replatform_ok` when terms permit container execution and only compliance or cost handling is needed. Unverifiable terms → `must_fix` with `class_unconfirmed: true` |
| `other` | Per decision test | No default — apply the decision test to the specific finding |

---

## Reporting Rules

### Per-blocker completeness

Every reported blocker carries, without exception:

1. **Category** — one of the six categories or `other` (with `category_rationale` when `other`).
2. **Evidence paths** — at least one file path grounding the detection. A blocker with zero evidence paths is not reportable; if the evidence cannot be named, the finding is not a determination.
3. **Reason** — a statement of why the item obstructs containerization or cloud migration, specific to the finding (not a restatement of the category name).
4. **Remediation class** — exactly one of `replatform_ok` / `must_fix`, plus `class_unconfirmed: true` and an unconfirmed note whenever the class was not settled by evidence.

### Credential value secrecy

For hardcoded credentials (including credentials embedded inside connection strings), the detected **value** never appears in any output — not in the blocker's `reason`, not in evidence details, not in the report, and not in conversation. This prohibition covers the value **in whole and in part**: no truncated prefixes, no partially masked forms (`pass***`), no character counts framed as hints, no reproducing the containing line verbatim. What **is** reported:

- the **file path** where the credential was found,
- the **category** (`hardcoded_credentials`),
- a **value-free description**, which may include the credential **type** (e.g. "database password embedded in a connection string", "API token assigned to a constant") and the location context (configuration key name, section) — provided none of these reproduce any part of the value.

When quoting evidence for any blocker, check the quoted content for embedded credentials first; if present, describe instead of quoting.

### Zero blockers — explicit statement

If **no** finding qualifies as a blocker, report that explicitly: state that no blockers were detected. This statement is mandatory regardless of whether the analysis produced other, non-blocker findings — silence is not a finding. An empty `blockers` list without the explicit statement is an incomplete output.

### Partial analysis disclosure

If parts of the source could not be read and were excluded from this module's scan:

- Report the excluded ranges at **path or directory granularity**, each with its reason, appended to `analysis.excluded_paths` (shared with tech stack detection — do not duplicate entries already recorded there; add any exclusion newly encountered by this module).
- Set `analysis.partial: true` and state explicitly that the blocker analysis is **partial**: undetected blockers may exist in the excluded ranges.
- Never present a partial scan's results as an exhaustive blocker inventory.

---

## Output Schema

This module produces the `blockers` block and updates the shared `analysis` envelope (partial-analysis state). Hold the structure in conversation context — the assessment phase writes no intermediate files.

```yaml
blockers:                          # empty list => the explicit zero-blocker statement is mandatory
  - id: string                     # sequential, e.g. "BLK-001"
    category: local_state | in_process_session | hardcoded_credentials |
              os_specific_api | process_model | licensing | other
    category_rationale: string | null   # required when category == other:
                                        # grounds for judging the item an obstruction
    remediation_class: replatform_ok | must_fix   # exactly one
    class_unconfirmed: bool        # true when the class could not be settled from evidence
                                   # (in which case remediation_class is must_fix — fail safe)
    evidence_paths: [string]       # >= 1 file path per blocker
    reason: string                 # why it obstructs containerization or cloud migration;
                                   # NEVER contains any part of a credential value

analysis:                          # shared envelope (initialized by tech stack detection)
  partial: bool                    # set true when this module excluded any unreadable range
  excluded_paths:
    - {path: string, reason: string}
```

**Reporting invariants:**

- Every blocker has `>= 1` entry in `evidence_paths`, exactly one `remediation_class`, and a finding-specific `reason`.
- `category_rationale` is non-null exactly when `category` is `other`.
- `class_unconfirmed: true` implies `remediation_class: must_fix`.
- No field of any blocker contains any part of a detected credential value.

---

## Edge Cases

### No blockers detected

An empty result is a legitimate outcome for a well-factored application. Emit the explicit zero-blocker statement (see Reporting Rules) — downstream modules (scoring, paths, report) rely on the distinction between "checked and found none" and "not checked". Non-blocker observations, if any, do not substitute for this statement.

### Remediation class cannot be determined

When the available evidence cannot settle the decision test — e.g. a P/Invoke target DLL whose user-mode/kernel-mode nature is unknown, or license terms that are referenced but not present in the tree — classify the blocker as `must_fix`, set `class_unconfirmed: true`, and attach a note that the class is not confirmed by evidence and what information would settle it. Never leave the class empty, and never default to `replatform_ok` on missing evidence: the safe direction is the stricter class.

### A finding matches multiple categories

Classify each blocker into the single most specific category. Precedence when patterns overlap: a connection string containing a credential is `hardcoded_credentials` (the secrecy rules must engage), not `local_state` or `other`; a Windows service dependency is `os_specific_api` when the finding is the API usage itself, and `process_model` when the finding is the multi-service lifecycle arrangement. If one root cause genuinely produces two independent obstructions (e.g. one component both writes local state and requires a hardware-bound license), report two blockers, each with its own evidence and reason.

### Log writes vs. state writes

Local file writes that are purely log output are not `local_state` blockers. Distinguish by content and configuration: logging-framework appenders/sinks writing to local files are logging; application code persisting domain data to files is state. When a write target's nature (state vs. regenerable cache vs. log) cannot be determined, report the blocker and let the class default per the decision test — and note what is unconfirmed. The persistent-vs-temporary mount decision for confirmed writes belongs to the path module, not here.

### One blocker spanning many files

A pattern repeated across many files (e.g. session writes in dozens of pages) is **one** blocker with multiple `evidence_paths` when it has one root cause and one remediation, not one blocker per file. List representative evidence paths (all, when few; a representative set plus a count, when very many).

### Unreadable files within a scanned category

If specific files matching a category's evidence patterns are unreadable (e.g. a `web.config` that cannot be opened), the corresponding determination may be incomplete: record the exclusion (path + reason), and where the unreadable file would have settled a class decision, apply the fail-safe (`must_fix` + `class_unconfirmed`) rather than assuming the benign outcome.

---

## Sources

- The Twelve-Factor App — processes (statelessness) and config externalization principles behind `local_state`, `in_process_session`, and `hardcoded_credentials`: https://12factor.net/processes , https://12factor.net/config
- ASP.NET session state modes (`InProc` default and alternatives): https://learn.microsoft.com/en-us/previous-versions/aspnet/ms178586(v=vs.100)
- Java Servlet specification — `<distributable/>` and session replication semantics: https://jakarta.ee/specifications/servlet/
- .NET platform interop (P/Invoke) and COM interop: https://learn.microsoft.com/en-us/dotnet/standard/native-interop/
- Windows registry access from .NET (`Microsoft.Win32.Registry`): https://learn.microsoft.com/en-us/dotnet/api/microsoft.win32.registry
- Java Native Interface (JNI) specification: https://docs.oracle.com/en/java/javase/21/docs/specs/jni/
- WebSphere Application Server container images (ILAN license for entitled customers): https://www.ibm.com/docs/en/was/9.0.5?topic=cloud-running-websphere-application-server-in-container
- WebSphere traditional distributed sessions (database persistence / memory-to-memory replication are server-side configuration): https://www.ibm.com/docs/en/was/9.0.5?topic=sessions-distributed
- Windows container limitations (no interactive desktop sessions; infrastructure requirements): https://learn.microsoft.com/en-us/virtualization/windowscontainers/deploy-containers/system-requirements
