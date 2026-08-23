# Module: Replatform Path

> **Part of:** [ecs-modernize](../SKILL.md)
> **Purpose:** Turn a Replatform strategy outcome into a concrete containerize-as-is path targeting ECS on EC2 — a static configuration template (fixed desired task count, fixed EC2 capacity derived from expected peak load, kept-vs-changed operational procedures), a per-stack containerization policy (base image, app-server bundling, configuration intake), minimal handling of must-fix blockers, persistent-vs-temporary mapping of local filesystem writes, and ALB sticky sessions for in-process session state — all under a strict no-application-code-change discipline
> **Prerequisites:** Scoring and Recommendation ([scoring-and-recommendation.md](scoring-and-recommendation.md)) — the Replatform path is presented from the `scoring`, `recommendation`, `tech_stack`, and `blockers` blocks; it is never assembled without them

This is a **path module**: unlike the orchestrator-neutral analysis modules, ECS-specific vocabulary is expected and deliberate here. Mapping the Replatform strategy onto its concrete ECS compute model — **ECS on EC2** — happens in this file (and only in the path modules); the scoring module hands over a strategy classification and nothing more.

**What Replatform means here.** The application code does not change. The existing application is packaged into a container image as-is and run on ECS on EC2 under a static, autoscaling-free configuration that mirrors how the current environment is sized and operated. Everything this module presents is built from work that requires no application code change — container image creation, configuration file intake, and ECS resource configuration — with exactly one sanctioned exception: the minimal remediation of must-fix blockers (see [Must-Fix Blocker Handling](#must-fix-blocker-handling)).

## Table of Contents

- [Inputs](#inputs)
- [Procedure](#procedure)
- [Criteria](#criteria)
  - [Target Compute Model: ECS on EC2](#target-compute-model-ecs-on-ec2)
  - [No-Code-Change Discipline](#no-code-change-discipline)
  - [Static Configuration Template](#static-configuration-template)
  - [Containerization Policy](#containerization-policy)
  - [WebSphere Traditional (tWAS) Containerization Specifics](#websphere-traditional-twas-containerization-specifics)
  - [Must-Fix Blocker Handling](#must-fix-blocker-handling)
  - [Local Filesystem Writes: Persistent vs Temporary](#local-filesystem-writes-persistent-vs-temporary)
  - [In-Process Sessions: ALB Sticky Sessions](#in-process-sessions-alb-sticky-sessions)
- [Windows_Container_Path](#windows_container_path)
  - [Presentation Decision Table](#presentation-decision-table)
  - [Compute Options for Windows Containers](#compute-options-for-windows-containers)
  - [Windows Base Image Selection Matrix](#windows-base-image-selection-matrix)
  - [Dependencies That Cannot Run in Windows Containers](#dependencies-that-cannot-run-in-windows-containers)
  - [Parallel Presentation: Linux Containerization via .NET Porting](#parallel-presentation-linux-containerization-via-net-porting)
  - [Windows_Container_Path Output Block](#windows_container_path-output-block)
- [Output Schema](#output-schema)
- [Edge Cases](#edge-cases)
- [Sources](#sources)

---

## Inputs

- **`tech_stack` block** (required) — languages, frameworks with classification families, runtimes with version and `eol` status, application servers, undetermined items. The containerization policy is keyed off these detections.
- **`blockers` block** (required) — every blocker with category, remediation class (`replatform_ok` / `must_fix`), evidence paths, and reason; or the explicit zero-blocker statement. The `local_state`, `in_process_session`, and `must_fix` entries drive dedicated sections of this path.
- **`scoring` + `recommendation` blocks** (required) — the Fit_Score with its per-dimension breakdown and the strategy classification. The Replatform path is presented regardless of which classification came out (both strategies always appear in the report), but its content is grounded in these results.
- **`analysis` envelope** (required) — target identity and partial-analysis state, which propagates into confidence notes.
- **Read-only discipline** — this module runs during the assessment phase: it reads no additional files beyond what Source_Analysis already collected, executes no commands, creates no files, and generates no IaC. Dockerfile or task-definition illustrations appear only as code blocks inside the Modernization_Report. Its output is held in conversation context for the report module.

Do not run this module before the scoring and recommendation module has produced its outputs (which in turn requires tech stack detection and blocker detection). A Replatform path assembled without them has no evidence base.

---

## Procedure

Run the steps in this order:

```
0. Confirm this file has been read in full       -> SKILL.md mandate before executing this module
1. Verify prerequisite outputs are present        -> tech_stack + blockers + scoring + recommendation
2. State the target compute model explicitly      -> ECS on EC2, every time the path is presented
   (Windows_Container_Path applicability is        (compute options under that path follow the
   judged in its own section)                       Windows_Container_Path section)
3. Partition the must_fix blockers                -> addressable (minimal remediation stated) vs
                                                     unresolved (user-resolution item stated)
4. Derive the containerization policy             -> three items — base image, app-server bundling,
   from the detected stack                           config intake — per detected language/FW/server;
                                                     generic policy when detections are undetermined
5. Map local filesystem writes                    -> persistent (external storage mount) vs temporary
                                                     (container-local), per write target; or the
                                                     explicit not-needed statement when none detected
6. Handle in-process session state                -> ALB sticky sessions + the session-loss constraint,
                                                     when the in_process_session blocker exists
7. Assemble the static configuration template     -> fixed desired task count, fixed EC2 capacity
                                                     derivation policy, kept-vs-changed ops procedures
8. Run the no-code-change audit                   -> every presented step is code-change-free, except
                                                     the minimal must-fix remediations from step 3
9. Assemble the output                            -> the replatform_path block for the report module
```

**Why this order:**

- Blocker partitioning (step 3) precedes everything content-bearing: an unresolved must-fix item changes what the path can promise, and the minimal remediations it yields are the only permitted exception the later no-code-change audit (step 8) checks against.
- The containerization policy (step 4) precedes the writes and session handling (steps 5–6) because the intake method chosen for configuration files (image bake-in / environment variables / EFS / SSM) constrains how write targets and session stores are discussed.
- The static configuration template (step 7) comes after the workload-shaping decisions (steps 4–6): task count and instance sizing policies depend on what the container actually carries (bundled app server, mounted volumes, sticky sessions).
- The audit (step 8) is a self-verification gate: if any presented step would require an application code change and is not a sanctioned minimal must-fix remediation, the path assembly is wrong — fix it before reporting.

---

## Criteria

### Target Compute Model: ECS on EC2

**Presentation rule (always explicit).** Whenever the Replatform path is presented, name **ECS on EC2** explicitly as the target compute model. Never leave the compute model implicit, and never substitute another model: the Replatform strategy as defined by this skill is containerize-as-is onto ECS on EC2 with a static configuration.

**Why ECS on EC2 (state the grounds in the report):**

- **Host control without host redesign.** Legacy applications frequently assume host-level facts — instance-attached storage layout, OS packages, generous memory footprints, long startup times. EC2 container instances keep those assumptions servable (instance type, AMI, volume layout are all choosable) without rewriting the application, which Fargate's opinionated runtime does not allow.
- **Static capacity is natural.** A fixed EC2 fleet with a fixed desired task count reproduces the current environment's capacity model one-to-one, which keeps existing capacity intuition and runbooks meaningful (see [Static Configuration Template](#static-configuration-template)).
- **No modern-runtime prerequisites.** The Rearchitect-side models (Express Mode, Fargate, Managed Instances) impose constraints — Linux-only images on managed hosts, graceful-shutdown pressure from instance cycling, single-port HTTP contracts — that an unmodified legacy application often cannot meet. ECS on EC2 imposes the fewest.

**Windows carve-out.** When the Windows_Container_Path applies (.NET Framework detections), the presentation of compute options for that variant — ECS on EC2 Windows instances AND Fargate Windows support, each with versions, licensing, and feature constraints — follows the [Windows_Container_Path](#windows_container_path) section's rules, not this one. This section governs the default (Linux-container) Replatform presentation.

**Boundary with `ecs-architect`.** This module presents capacity **derivation policy** (how to size), never concrete design values: capacity-provider strategy, task sizing numbers, and network design are delegated to `ecs-architect` by name in the report, exactly as the Rearchitect path does.

### No-Code-Change Discipline

**The composition rule.** Compose the presented Replatform procedure exclusively of work that requires **no application code change**:

| Permitted work | Examples |
|---|---|
| Container image creation | Writing a Dockerfile around the existing deployable artifact; choosing a base image; setting the entrypoint to the existing start command |
| Configuration file intake | Baking existing config files into the image; mapping them to environment variables at the container boundary; mounting them from EFS; loading them from SSM Parameter Store — all without editing application code that reads them |
| ECS resource configuration | Task definition, service, cluster, capacity, load balancer, target group, volume, and log configuration |

**The single exception.** Minimal remediation of `must_fix` blockers — the items that cannot run inside a container at all — is permitted and presented per the [Must-Fix Blocker Handling](#must-fix-blocker-handling) rules. Nothing else justifies a code change inside this path: a change that would merely *improve* the application (externalizing sessions, adding health endpoints, upgrading frameworks) belongs to the Rearchitect path and must not leak into this one.

**The audit.** Before assembling the output, walk every presented step and verify it falls in the permitted table or is a sanctioned minimal must-fix remediation. The output's `code_change_free` invariant asserts this audit passed.

### Static Configuration Template

The recommended configuration is **static**: no autoscaling, fixed counts, capacity planned once from expected peak load. Present all three elements below every time.

**1. Fixed desired task count.**

- Set the ECS service's `desiredCount` to a **fixed value** — no scaling policies attached.
- **Derivation policy:** start from parity with the current environment — the number of application instances (VMs / EC2 hosts / app-server JVMs or worker processes) serving the workload today, as evidenced by the deployment configuration Source_Analysis collected. Parity preserves the concurrency and failure characteristics the operation already understands.
- When the current instance count is not in evidence, state that the count must be supplied by the user from the live environment — do not invent one.

**2. Capacity plan without autoscaling (fixed EC2 instance count).**

Present the **derivation policy** for a fixed number of EC2 container instances, based on expected peak load:

1. Establish the per-task resource footprint from the current environment's sizing (the CPU/memory of the hosts serving one application instance today), since the unmodified application's appetite does not change by being containerized.
2. Multiply by the fixed desired task count to get the total steady-state resource demand **at expected peak load** — the sizing basis is the peak, not the average, because there is no autoscaling to absorb bursts.
3. Divide by the capacity of the chosen instance type to get the base instance count, then add fixed headroom: at least **one spare instance's worth of capacity** so that a single instance failure or a rolling task replacement does not leave the service under `desiredCount` (an N+1 policy), spread across at least two Availability Zones.
4. Present the arithmetic as a **policy with the current-environment inputs named** — the concrete instance-type selection and final numbers are `ecs-architect`'s detailed design, delegated by name.

**3. Operational procedures: kept vs changed.**

Distinguish, explicitly and item by item, which existing operational procedures survive the move and which must change. Ground each row in what Source_Analysis observed (deployment scripts, server configs); the canonical split:

| Typically **kept** (unchanged intent, same interface) | Typically **changed** (new mechanism required) |
|---|---|
| Application-level runbooks (functional checks, business-calendar operations) | Deployment: host file-copy / app-server console deploys become image build + ECS service update |
| Monitoring thresholds and alert semantics (what "unhealthy" means) | OS patching: in-place host patching becomes AMI/container-instance replacement and base-image refresh |
| Backup procedures for external data stores (databases were external before and stay external) | Log access: host login + log-file tailing becomes the container log driver (e.g. CloudWatch Logs) |
| Escalation paths and on-call structure | Restart procedures: app-server service restarts become ECS task stop/replace |
| | Host login-based diagnostics: direct SSH workflows must be re-based (ECS Exec, instance access policies) |

An item that cannot be classified from the evidence is presented as **needs-confirmation**, not silently placed in either column.

### Containerization Policy

For the detected language, framework, and application server, present **all three** policy items, each with its grounds. The policy is keyed by the `tech_stack` detections — never by guesswork about what "typical" applications need.

**Item 1 — Base image selection policy.**

| Detected stack | Base image policy | Grounds |
|---|---|---|
| Java + standalone-capable framework (e.g. Spring Boot executable JAR) | Official OpenJDK-distribution runtime image (e.g. `eclipse-temurin` JRE) at the **same major Java version** as the detected runtime | The artifact embeds its server; only a matching JRE is needed. Version parity is non-negotiable: the code is not changing, so the runtime must not either |
| Java WAR + Tomcat | Official `tomcat` image at the **matching Tomcat major and Java version** | The WAR expects the container's servlet API level; official images pin both coordinates |
| Java + WebSphere traditional (tWAS) | IBM's traditional WAS container image `icr.io/appcafe/websphere-traditional` at the matching server version line (9.0.5.x / 8.5.5.x) — see [WebSphere traditional specifics](#websphere-traditional-twas-containerization-specifics) | tWAS descriptors (`ibm-web-bnd.xml` and family) and any `com.ibm.websphere.*` API usage bind the app to traditional WAS behavior; substituting Liberty or Tomcat would demand code/config rework, which this path forbids |
| Java + WebSphere Liberty / Open Liberty | `icr.io/appcafe/websphere-liberty` (or `open-liberty`) at the matching version and feature set | An app already on Liberty replatforms onto Liberty's official container images directly — carry over the existing `server.xml` feature configuration |
| Java + WebLogic | Oracle's WebLogic container images at the matching server version | Vendor descriptors (`weblogic.xml`) bind the app to that server's behavior; same no-substitution rule |
| .NET (Core / 5+) | `mcr.microsoft.com/dotnet/aspnet` at the matching .NET version | Cross-platform .NET runs on Linux images as-is |
| .NET Framework (4.x and earlier) | Windows base images — governed by the [Windows_Container_Path](#windows_container_path) base-image matrix (.NET Framework version × IIS dependency) | .NET Framework does not run on Linux; the Windows section owns this selection |
| Other detected languages | Official runtime image of the detected language at the matching version | Same version-parity rationale |

**Item 2 — Application-server bundling judgment (with grounds).**

Decide whether the application server is bundled into the container image, and state the grounds:

- **Bundle** when the deployable artifact requires an external server process to run (WAR files, IIS-hosted apps, vendor app servers): the server IS the container's main process, configured via the server-included base image above. One container = one server instance = one app deployment — do not reproduce multi-app-per-server topologies inside a single container.
- **Do not bundle** when the artifact embeds its server (Spring Boot executable JAR, ASP.NET Core self-hosted/Kestrel): adding an external server would change the runtime architecture, which this path forbids.
- **Undetermined server** → see the generic-policy rule below.

**Item 3 — Configuration file intake method.**

Map each configuration artifact Source_Analysis found to exactly one intake method, with the decision criteria stated:

| Method | Choose when | Cautions |
|---|---|---|
| **Bake into image** | The value is identical across environments and secret-free (static framework config, servlet descriptors) | Never bake credentials; environment-specific values baked in force per-environment images — avoid |
| **Environment variables** | The value varies per environment, is small, and the app already reads it from an overridable source (JVM system properties, .NET config builders, container-aware config files) — overriding at the container boundary requires no code change | If the app can only read files, use a file-based method instead — do not modify code to read env vars (that is a Rearchitect item) |
| **Amazon EFS mount** | The config is a file the app insists on reading from a path, is large, or is shared/updated across tasks without image rebuilds | Mount read-only for config; note EFS latency is fine for read-at-startup config |
| **SSM Parameter Store (and Secrets Manager for secrets)** | The value is a secret or centrally managed parameter; ECS injects it as an environment variable or the entrypoint materializes it into the expected file at startup | Secrets never go into the image or the task definition in plain text; an entrypoint script that writes a config file from SSM values is containerization work, not an app code change. **The task execution role must be extended** with `ssm:GetParameters` / `secretsmanager:GetSecretValue` (plus `kms:Decrypt` for a customer-managed key) for the referenced parameters/secrets — `AmazonECSTaskExecutionRolePolicy` alone does not grant it, so task-definition `secrets` fail to pull at task start without the added statement |

**Undetermined stack items (generic policy + explicit limitation).** When the language, framework, or application server is reported as undetermined by tech stack detection, present a **generic containerization policy grounded only in the items that WERE determined** (e.g. language known but server unknown → language-appropriate runtime image, bundling judgment deferred), and state **explicitly** that the policy is limited, naming the undetermined item(s) that limit it. Never fabricate a stack-specific policy from a guess, and never skip the policy section because something is undetermined.

### WebSphere Traditional (tWAS) Containerization Specifics

When tech stack detection reports **IBM WebSphere Application Server traditional** as the application server, the containerize-as-is route runs the app on IBM's traditional WAS container image. Present all of the following whenever this stack applies — these are the tWAS-specific instantiations of the three policy items plus the licensing and boundary rules:

- **Base image and build model.** Derive the application image `FROM icr.io/appcafe/websphere-traditional` at the version line matching the current cell (9.0.5.x or 8.5.5.x; ICR images are UBI-based and pullable without authentication or rate limits). Bake the application EAR/WAR and its configuration into the image at build time. **Never configure a running container** through the admin console or interactive wsadmin — changes made to a running container are lost when a new container is spawned; the image is the unit of configuration ([WASdev/ci.docker.websphere-traditional](https://github.com/WASdev/ci.docker.websphere-traditional)).
- **Configuration intake is properties-file based.** tWAS server configuration (data sources, JVM settings, session management, security aliases) is carried into the image as **properties files** — `COPY` them into `/work/config/` and apply them at build time with `RUN /work/configure.sh`, which runs against a stopped server and applies `*.props` in alphabetical order (numeric filename prefixes order dependent properties). Extract the current values from the existing cell with wsadmin's `extractConfigProperties`; `applyConfigProperties` is the corresponding apply command. This is configuration work, not application code change, so it stays inside the no-code-change discipline. Environment-specific values and secrets follow the parent path's intake table (environment variables / SSM / Secrets Manager materialization by the entrypoint) rather than being baked in.
- **One application per server per container.** IBM's documented best practice is an image that adds **a single application and its configuration**; do not reproduce a multi-application tWAS cell topology inside one container. One image = one server instance = one app deployment, consistent with the parent bundling judgment. A multi-app cell becomes multiple images/services; present that decomposition as part of the path.
- **Cell topology does not transfer.** Deployment manager / node agent / cluster structures are replaced by ECS constructs (service `desiredCount`, ALB): the containerized server is a standalone server profile. Runbooks tied to the dmgr console land in the "changed" column of the operational-procedures table.
- **Session persistence.** tWAS server-side session persistence — database persistence and DRS memory-to-memory replication (the latter a Network Deployment clustering feature), both of which the 8.5.5 and 9.0 lines document — is cell configuration; database session persistence CAN be reproduced via the properties-file configuration, which softens the parent path's sticky-session constraint when it exists today. Which mechanism a given cell uses, and what the target version supports, is a per-version fact to confirm against the live IBM documentation rather than assumed. Whether it exists is usually not evidenced in the source tree — carry the user-confirmation note from blocker detection through to this presentation.
- **Licensing (user action).** The tWAS container images are ILAN-licensed for **entitled** WebSphere customers; running them requires existing WAS entitlement, and container licensing metrics must be confirmed. Flag entitlement/metric confirmation as a user action, exactly like the licensing must-fix remediation of the parent path. Note that traditional WAS entitlement includes Liberty entitlement — relevant if the user later weighs the Rearchitect-side Liberty migration.
- **Accelerator note — IBM assessment tooling, assessment output only.** IBM's Transformation Advisor and the Migration Toolkit for Application Binaries (binary scanner) analyze tWAS applications and report per-application findings — proprietary-API usage, migration complexity, effort estimates — which is useful input to this path's judgments. **Their generated migration artifacts are not usable here:** Transformation Advisor's generated bundle (`server.xml`, `pom.xml`, Containerfile, Application CR) targets **Liberty**, and the CR targets OpenShift — that is the Rearchitect-side Liberty migration, not containerize-as-is on tWAS ([TA migration artifacts](https://www.ibm.com/docs/en/cta?topic=migration-artifacts)). Present the tooling as an optional *assessment* accelerator whose artifact generation is out of scope for this path; running it is the user's action.
- **Boundary — Liberty is not the Replatform target for a tWAS app.** Moving a tWAS-hosted application onto WebSphere Liberty (or Open Liberty) requires configuration-model conversion and often code changes (proprietary `com.ibm.websphere.*` API replacement) — that is a **Rearchitect modernization item** ([rearchitect-path.md](rearchitect-path.md)), never silently substituted into this path. Reference it; do not perform it here.

### Must-Fix Blocker Handling

Blockers classified `must_fix` by blocker detection cannot run inside a container even unmodified — they gate the Replatform path too. Handle **every one of them, without exception**, in exactly one of two ways:

**1. Addressable — present the minimal remediation.** When a remediation policy CAN be stated, include the **minimal** remediation for that blocker in the Replatform path presentation, per blocker, with its evidence. Minimal means: the smallest change that makes the component run in a container — never an opportunistic modernization. Representative minimal remediations:

| must_fix category (examples) | Minimal remediation to present |
|---|---|
| Container-incompatible process model — host-supervised multi-process arrangement | Split the processes across separate containers/task definitions with unchanged binaries, or run the existing supervisor as the container entrypoint where its children are container-safe; only entry-point wiring changes |
| Host scheduler dependence (cron / Windows Task Scheduler jobs) | Recreate the schedule as separate ECS scheduled tasks invoking the existing commands unchanged |
| Licensing-constrained component pinned to specific hosts | Confine tasks to designated licensed container instances (task placement constraints on dedicated instances) so the license terms keep being met; flag license-term confirmation as a user action |
| Kernel-mode / hardware-bound dependency | Usually NOT addressable → unresolved item (below) |

**2. Not addressable — present the unresolved item.** When no remediation policy can be stated from the evidence, present the blocker **explicitly as an unresolved item requiring user resolution** — with its ID, category, evidence, and why no remediation can be offered.

**Never suppress the path.** The existence of unresolved items — however many — never causes the Replatform path presentation to be omitted or truncated. The path is presented in full, with its unresolved-items list carried visibly, so the user sees exactly what stands between them and this path. Skipping the presentation "because it's blocked anyway" is a violation.

### Local Filesystem Writes: Persistent vs Temporary

**When Source_Analysis detected local filesystem writes** (`local_state` blockers, plus any write targets recorded in their evidence):

1. **Classify every detected write target** into exactly one of:
   - **Persistent** — data that must survive task replacement (business data, user uploads, durable application state): mount external storage — **Amazon EFS** as the default policy — at the written path, so the unchanged application keeps writing to the same path while the data lands on durable shared storage.
   - **Temporary** — data whose loss on task replacement is acceptable (scratch files, extracted work dirs, regenerable caches): container-local writes are acceptable; note the task's ephemeral storage bounds.
2. **Present the mapping per write target** — each target path with its classification, the treatment (EFS mount point vs container-local), and the evidence that grounded the classification. A blanket statement ("mount EFS somewhere") is not a mapping.
3. **Fail-safe when unclassifiable:** a write target whose persistence requirement cannot be determined from the evidence is treated as **persistent** (external mount), with a note that the classification is unconfirmed — losing regenerable data costs a rebuild; losing durable data costs the data.
4. Log streams written to local files are ordinarily **temporary** at the storage level (redirect to the container log driver at the ECS configuration layer); if the application cannot log to stdout/stderr without code change, keep the file write and collect via a sidecar or log-router configuration — configuration work, not code work.

**When Source_Analysis detected no local filesystem writes:** state **explicitly** that persistent-data external-storage mounting is judged **not needed at this time**, and state the grounds — no local filesystem writes were detected by Source_Analysis (name the zero-finding statement from blocker detection as the evidence). Silence is not an option: the report reader must see that the question was asked and answered, not overlooked.

### In-Process Sessions: ALB Sticky Sessions

**When the `in_process_session` blocker is present** (the application holds authoritative session state in process memory), the Replatform path presents the no-code-change countermeasure **and its constraint, always together**:

- **Countermeasure — ALB sticky sessions (session affinity).** Enable target-group stickiness on the Application Load Balancer (duration-based cookie `AWSALB`, or application-based stickiness reusing the app's existing session cookie such as `JSESSIONID` / `ASP.NET_SessionId`), so each user's requests keep landing on the task holding their session. This is pure load-balancer configuration; the application is unchanged.
- **Constraint — session loss on task stop or replacement (never omit).** Sticky sessions pin users to a task; they do not replicate state. When that task stops or is replaced — deployment, instance failure, manual restart, or any rebalancing — **every session held on that task is lost**, and the affected users are logged out or lose in-flight state. Present this constraint in the same breath as the countermeasure, and note its operational consequences for the static template: deployments should be scheduled in low-traffic windows, and the true fix (session externalization) is a Rearchitect modernization item, referenced but not performed here.

When no `in_process_session` blocker exists, this section of the presentation states that no in-process session state was detected and sticky sessions are not required (grounded in the blocker detection output).

---

## Windows_Container_Path

This is a **submodule of the Replatform path** — not a separate module. Its assessment and presentation knowledge lives in this Reference_File by design; the knowledge for *building* the Windows target environment (Windows_Environment_Terraform generation) lives in [windows-environment-build.md](windows-environment-build.md) and is an execution module behind the Execution_Gate. This section decides **whether and how** the Windows container route is presented; it never builds anything.

**What the Windows_Container_Path is.** The no-code-change containerization route for **.NET Framework (4.x and earlier)** applications: since .NET Framework does not run on Linux, the Replatform discipline (containerize as-is, no application code change) leads to **Windows containers on ECS**. Everything in the parent Replatform path — static configuration template, must-fix handling, local-writes mapping, sticky sessions — applies to this variant unchanged; this section adds the Windows-specific judgments: whether to present the path at all, which compute options exist for Windows containers, which Windows base image to select, which dependencies rule the path out, and when to present the Linux-porting alternative in parallel.

### Presentation Decision Table

Whether and how the Windows_Container_Path appears is a **deterministic decision** over five inputs from the prerequisite blocks — never a judgment call:

| Input | Source |
|---|---|
| .NET Framework (4.x and earlier) runtime detected? | `tech_stack` (runtime classification `dotnet_framework`) |
| Windows-container-incompatible dependency present? (desktop GUI / hardware driver / kernel-mode) | `blockers` (see [Dependencies That Cannot Run in Windows Containers](#dependencies-that-cannot-run-in-windows-containers)) |
| Fit_Score vs Rearchitect_Threshold | `scoring` + `recommendation.thresholds` |
| Windows-specific API blockers ≥ 1? (Windows registry, Windows services, COM, P/Invoke to Win32) | `blockers` (category `os_specific_api` with Windows-specific evidence) |
| Do ALL Windows-specific API blockers have documented .NET (Core / 5+) alternatives? | judged per blocker against the [alternatives table](#parallel-presentation-linux-containerization-via-net-porting) |

Evaluate the rows **in order**; the first matching row decides. Rows 1 and 2 are gates; rows 3 and 4 partition the remaining cases **that carry a numeric Fit_Score**. When the Fit_Score could not be computed (`fit_score: null` — e.g. compiled-artifacts with no readable source), the numeric comparisons in rows 3 and 4 do not apply: present the Windows_Container_Path as an **`option`** (the conservative choice, consistent with the [no-score handling](scoring-and-recommendation.md#no-score-handling)) when .NET Framework is detected with no container-incompatible dependency, and state that the Fit_Score could not be computed.

| # | Condition | Judgment (`mode`) |
|---|---|---|
| 1 | .NET Framework NOT detected | **Not presented** (`presented: false`, `mode: null`). The Windows_Container_Path never appears for applications without a .NET Framework runtime detection. |
| 2 | .NET Framework detected ∧ ≥ 1 Windows-container-incompatible dependency | **`not_applicable`** — this condition **takes precedence over every score and blocker condition below**. Report the applicability judgment as "not applicable" together with the full list of blocking dependencies (their blocker IDs and evidence), and do **not** present the Windows_Container_Path as a Replatform option. The judgment and its grounds appear inside the Replatform path details; the route itself is not offered. |
| 3 | .NET Framework detected ∧ no incompatible dependency ∧ (Fit_Score < Rearchitect_Threshold ∨ Windows-specific API blockers ≥ 1) | **Presented as a Replatform `option`** — a first-class choice within the Replatform path. The Windows-API-blocker arm applies **regardless of the Fit_Score value**: even a high-scoring application with registry/Windows-service/COM dependencies gets the Windows route offered, because those dependencies make Linux containerization impossible without code change. |
| 4 | .NET Framework detected ∧ no incompatible dependency ∧ Fit_Score ≥ Rearchitect_Threshold ∧ zero Windows-specific API blockers | **Presented as a `variant`** — the Requirement-6 strategy recommendation is **not changed** (Rearchitect stays recommended); the Windows container route is presented inside the Replatform path details as the variant that applies *if the user chooses Replatform anyway*. |

**Parallel-presentation rule (applies on top of rows 3 and 4):** when the path is presented (`option` or `variant`) **and** every detected Windows-specific API blocker has a documented .NET alternative — a condition that is **vacuously satisfied when zero such blockers exist** — additionally present the Linux-porting alternative per [Parallel Presentation](#parallel-presentation-linux-containerization-via-net-porting). When at least one Windows-specific API blocker has no .NET alternative, state explicitly that the Linux-porting parallel is not offered and name the blocker(s) without alternatives.

**Never silently absent.** Whichever row fires, the report reader must be able to see that the judgment happened: rows 2–4 produce visible content inside the Replatform path details (the `not_applicable` grounds, the option, or the variant); only row 1 produces no Windows section at all — and only because there is no .NET Framework detection to explain.

### Compute Options for Windows Containers

When the Windows_Container_Path is presented (`option` or `variant`), present **both** compute options — never just one — and for **each** option state all three items: available Windows Server versions, licensing considerations, and feature constraints. Verify versions and constraints against the cited AWS documentation at presentation time; these facts change.

**Option A — ECS on EC2 with Windows container instances.**

| Item | Content to present |
|---|---|
| Windows Server versions | Amazon ECS-optimized Windows AMIs: **Windows Server 2025 Full / Core**, **2022 Full / Core**, **2019 Full / Core** (Windows Server 2016 Full still exists but is not recommended — it cannot receive current Docker runtime updates). **Host/image coupling:** with process isolation, the container base image's Windows version must match the host OS version — the AMI choice and the base-image tag (ltsc2019 / ltsc2022 / ltsc2025) are one decision, enforceable with the placement constraint `attribute:ecs.os-family == WINDOWS_SERVER_<release>_<FULL/CORE>`. Confirm the chosen base image publishes a tag for the selected release before committing to it — e.g. .NET Framework 4.x has no `4.8` ltsc2025 tag (use `4.8.1-windowsservercore-ltsc2025` on Windows Server 2025) |
| Licensing considerations | License-included EC2 Windows instances carry the Windows Server license cost in the instance price. BYOL is possible under Microsoft's licensing terms (typically via EC2 Dedicated Hosts) — flag license-position confirmation as a user action, exactly like the licensing must-fix remediation in the parent path |
| Feature constraints | Windows and Linux containers cannot share container instances — keep Windows tasks on Windows instances (placement constraint `ecs.os-type == 'windows'`; separate clusters recommended). IAM roles for tasks require instance-launch configuration and a credential proxy that **occupies port 80 on the instance** (use ALB dynamic port mapping for HTTP-80 services). Windows base images are large (~9 GiB) — plan instance storage accordingly. Several task-definition parameters behave differently or are unsupported on Windows (see the task-definition differences documentation) |

**Option B — Fargate Windows support.**

| Item | Content to present |
|---|---|
| Windows Server versions | `runtime_platform` operating system families: **Windows Server 2019 Full / Core** and **Windows Server 2022 Core / Full** (no Windows Server 2025 on Fargate at the time of writing — re-verify) |
| Licensing considerations | **AWS handles the OS license management — no additional Windows Server licenses are needed**; the license cost is included in Fargate Windows pricing (charged as an OS license fee component alongside vCPU/memory) |
| Feature constraints (features **unavailable** on Fargate Windows — present this list explicitly) | Amazon EFS volumes; Amazon EBS volumes; Amazon FSx; gMSA (Group Managed Service Accounts); ENI trunking; App Mesh integration; FireLens log routing; the Fargate **Spot** capacity provider; image volumes (Dockerfile `VOLUME` is ignored — use bind mounts); task-definition parameters `maxSwap` / `swappiness` / `environmentFiles`; container restart policies; task-level CPU/memory parameters are ignored (specify container-level resources); a service's `platformFamily` cannot be updated after creation. Linux and Windows containers need separate task definitions |

**Consequences for this path (state them, don't leave them implicit):**

- **Persistent write targets change treatment on the Windows variant.** The parent path's default persistent-data treatment (Amazon EFS) does not transfer: EFS is NFS-based and not supported for Windows containers. On **ECS on EC2 Windows**, the durable-shared-storage counterpart is **Amazon FSx for Windows File Server** (SMB) via ECS's FSx for Windows File Server volumes (EC2 launch type only). On **Fargate Windows**, FSx, EFS, and EBS volumes are all unavailable — a workload with persistent write targets cannot be served there; present ECS on EC2 Windows as the compatible compute option and say why.
- **Windows Integrated Authentication / gMSA rules out Fargate.** When blocker detection reports AD-backed auth (`os_specific_api`: `<authentication mode="Windows">` / `windowsAuthentication` / `Integrated Security=SSPI` / `Trusted_Connection`), the app needs a group Managed Service Account (gMSA), which is **not supported on Windows containers on Fargate** — it is an ECS-on-EC2-Windows-only feature ([gMSA for Windows containers](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/windows-gmsa.html)). Present **ECS on EC2 Windows as the only compatible compute option** in that case, and carry the gMSA/CredSpec setup as a user prerequisite through to the environment build (recommending Fargate to an AD-dependent app would fail authentication at verification).
- **Sticky sessions are unaffected.** The ALB stickiness countermeasure from the parent path is load-balancer configuration and works with both Windows compute options.
- **Sizing follows the parent template.** The static configuration template (fixed task count, peak-based capacity, N+1) applies to Windows instances the same way; concrete instance-type and sizing numbers remain delegated to `ecs-architect`.

### Windows Base Image Selection Matrix

When `tech_stack` determined **both** the .NET Framework version **and** the presence/absence of an IIS dependency (`web.config` + IIS-hosted evidence), present the base-image selection from this matrix **with the grounds stated** (the determined version and the determined IIS finding, with their evidence paths):

| .NET Framework version | IIS dependency | Base image policy | Grounds |
|---|---|---|---|
| 4.x | Yes (IIS-hosted web app: ASP.NET Web Forms / MVC / WCF under IIS) | `mcr.microsoft.com/dotnet/framework/aspnet:4.8` (pick the `-windowsservercore-ltsc2019` / `-ltsc2022` tag matching the chosen host/platform version). **On Windows Server 2025 there is no `4.8` ltsc2025 tag** — the 4.x-family image is `4.8.1-windowsservercore-ltsc2025` (4.8.1 is the latest servicing release of the terminal 4.x line and runs the same 4.x apps); verify current tags on MCR before selecting | The ASP.NET image ships IIS with ASP.NET registered — the app deploys into it unchanged. .NET Framework 4.8/4.8.1 is the in-place-update terminal line of the 4.x family: it runs applications targeting any 4.x version, so one image serves the whole family |
| 4.x | No (console app, self-hosted service, Windows-service worker) | `mcr.microsoft.com/dotnet/framework/runtime:4.8` (same Windows-version tag rule) | Runtime-only image — carrying IIS for a non-IIS app would violate the minimal-image principle and widen the surface without serving the artifact |
| 3.5 | Yes | `mcr.microsoft.com/dotnet/framework/aspnet:3.5` | Same ASP.NET/IIS rationale at the 3.5 runtime level; 4.8 images do not serve 3.5-targeted apps (3.5 is a separate CLR lineage, not an in-place 4.x update) |
| 3.5 | No | `mcr.microsoft.com/dotnet/framework/runtime:3.5` | Same runtime-only rationale |

**Matrix rules:**

- All .NET Framework images are **Windows Server Core**-based — .NET Framework is not supported on Nano Server, so no Nano option exists in this matrix.
- The Windows-version tag is not a free choice: on ECS on EC2 it must match the container instance OS (process isolation); on Fargate it must match the chosen `runtime_platform` family. State the coupling when presenting the selection.
- **App-server bundling is decided by this matrix** for the Windows path: the IIS-dependency column *is* the bundling judgment (IIS-hosted → the `aspnet` image bundles IIS; non-IIS → no server bundled), consistent with the parent [Containerization Policy](#containerization-policy) Item 2.

**Undetermined-item handling (never guess, never suppress the path).** When **either** the .NET Framework version **or** the IIS-dependency finding is undetermined, state explicitly that a base-image selection policy **cannot be presented**, name exactly which item(s) are missing and what evidence would determine them (e.g. `TargetFramework` in a project file for the version; `web.config` with `system.webServer` or IIS deployment artifacts for IIS) — and **still present the Windows_Container_Path itself** with its compute options and every other section. A missing base-image policy limits the presentation; it never cancels it.

### Dependencies That Cannot Run in Windows Containers

Windows containers remove the Linux-incompatibility problem for .NET Framework — they do **not** make everything containerizable. The following dependency classes cannot run in Windows containers (no interactive desktop session, no hardware passthrough, no kernel-mode loading):

| Dependency class | Representative evidence |
|---|---|
| Desktop GUI frameworks used for display (WinForms / WPF windows, `ShowDialog`, message pumps, tray icons) | `System.Windows.Forms` / `PresentationFramework` references in a component that runs headless-incompatible UI at runtime |
| Hardware drivers / direct device access | device driver installers bundled with the app, serial/USB device access, vendor SDKs requiring physical hardware |
| Kernel-mode components | kernel driver (`.sys`) loading, filter drivers, services flagged as kernel-mode |

**Reporting rule (Req 8.9).** Each such dependency is reported as a **must-fix Blocker** — `remediation class must_fix`, with its category, the grounding evidence file path(s), and the reason it cannot run in a Windows container. These findings originate in blocker detection ([blocker-detection.md](blocker-detection.md)); this section's job is to surface every one of them **inside the Replatform path details** as the grounds for the applicability judgment. Note the boundary: a mere *reference* to a GUI assembly (e.g. `System.Drawing` used for server-side image manipulation) is not by itself a display dependency — the blocker exists when the evidence shows runtime UI/hardware/kernel behavior; an unclear case follows blocker detection's fail-safe (must_fix with an unconfirmed note).

**Applicability consequence (Req 8.10).** When at least one such blocker is reported, the decision table's row 2 fires: the Windows_Container_Path applicability is reported as **"not applicable"**, the report carries the complete list of the blocking dependencies (IDs + evidence), and the path is **not** offered as a Replatform option. This precedence is absolute — no Fit_Score value and no Windows-API-blocker configuration overrides it. The rest of the Replatform path (Linux-container presentation where possible, must-fix handling, unresolved items) is still presented in full, per the parent path's never-suppress rule.

### Parallel Presentation: Linux Containerization via .NET Porting

**Condition.** The Windows_Container_Path is presented (`option` or `variant`) **and** every detected Windows-specific API blocker has a documented .NET (Core / 5+) alternative. Zero Windows-specific API blockers satisfies this vacuously — a .NET Framework app with no Windows API dependencies is the *easiest* porting candidate, so the parallel is always presented then.

**What to present.** Alongside — not instead of — the Windows container route: the option of **porting the application to modern .NET (.NET 8 LTS / .NET 10) and containerizing on Linux**, with:

1. **The per-blocker alternative mapping** — each Windows-specific API blocker paired with its .NET alternative, so the feasibility claim is grounded:

   | Windows-specific API dependency | Documented .NET alternative |
   |---|---|
   | Windows registry access (settings storage) | `Microsoft.Extensions.Configuration` providers (appsettings/environment variables) |
   | Windows Service hosting | Generic Host `BackgroundService` (a plain container process on ECS) |
   | Windows Event Log | `ILogger` to stdout/stderr → container log driver |
   | `System.Web` / IIS-coupled pipeline | ASP.NET Core middleware pipeline on Kestrel |
   | WCF service hosting | CoreWCF (compatibility path) or gRPC (redesign) |
   | MSMQ | Amazon SQS or another broker (integration change, no Windows dependency) |
   | `System.Drawing` (server-side imaging) | `ImageSharp` / `SkiaSharp` |
   | COM interop, P/Invoke into Win32-only APIs | **Frequently no cross-platform alternative** — when any such blocker lacks one, the condition fails: state that the Linux-porting parallel is not offered and name the blocker(s) |

2. **The remediation-effort classification** on the **three-tier scale (small / medium / large) defined in [rearchitect-path.md](rearchitect-path.md)'s Effort Scale section** — that scale is the single definition; classify the port against it by reference. A full .NET Framework → modern .NET port of a web application is typically **large** (framework-level change per that scale); a small self-contained console worker can land at **medium**. Classify from the actual findings (count and spread of Windows-API evidence, framework surface), not from the category name.

3. **AWS Transform for .NET as an optional accelerator** — include it in the parallel presentation with its scope and its effect on effort:
   - **Applicability:** source .NET Framework 3.5+ / .NET Core 3.1 / .NET 5.x+; target .NET 8 (LTS) / .NET 10; C# only. Automation scope includes Entity Framework / ADO.NET migration, MVC Razor Views → ASP.NET Core Razor Views, NuGet version resolution, and Web Forms UI → Blazor Server ([AWS Transform for .NET](https://docs.aws.amazon.com/transform/latest/userguide/dotnet.html) — re-verify coverage against this live source before asserting it).
   - **Effort effect:** note that adoption **may lower the effective effort classification** (e.g. a *large* port trending toward *medium* for the automated portion). The classified tier itself remains the manual-effort judgment; the reduction is a note, never a silent reclassification — same rule as rearchitect-path.md.
   - **Assessment/execution boundary (design decision 8):** in the Assessment_Phase this is a **recommendation in the report only**. No Transform job is proposed for adoption, scoped, or started here. Actual transformation is executed exclusively by the code transformation module ([code-transformation.md](code-transformation.md)) after Execution_Gate passage.

**Why parallel, not replacement.** The Windows container route is the no-code-change route; the port is a code-change route that buys Linux economics (no Windows licensing, smaller images, Fargate Spot, EFS, the full Linux feature surface) at remediation cost. Presenting both with their effort and constraint profiles is what lets the user make the trade — the recommendation from Requirement 6 is not altered by this section either way.

### Windows_Container_Path Output Block

This submodule contributes the `windows_container_path` block, carried **inside** the Replatform path's output for the report module (the report renders it as a subsection of "Replatform path details"; when `mode: not_applicable`, the report carries the judgment and its grounding blockers instead of the option):

```yaml
windows_container_path:
  presented: bool                  # false when .NET Framework not detected (row 1) or not_applicable (row 2)
  mode: option | variant | not_applicable | null
    # option         = presented as a Replatform choice (decision table row 3)
    # variant        = recommendation unchanged; presented as the variant when Replatform is chosen (row 4)
    # not_applicable = ruled out by Windows-container-incompatible dependencies (row 2 — takes precedence)
    # null           = .NET Framework not detected (row 1)
  blocking_dependencies: [string]  # blocker IDs grounding a not_applicable judgment (empty otherwise)
  base_image_policy: {framework_version: string, iis: bool, image: string} | null
    # null when the version or the IIS finding is undetermined — then the undetermined
    # items MUST be named below and the path is still presented
  base_image_undetermined_items: [string]   # REQUIRED non-empty when base_image_policy is null
                                            # and mode is option/variant: the missing item(s)
                                            # and what evidence would determine them
  dotnet_port_alternative:
    {feasible: bool, effort: small | medium | large,
     aws_transform_applicability: string | null} | null
    # present (feasible: true) when all Windows API blockers have .NET alternatives
    #   (vacuously true at zero blockers); effort uses rearchitect-path.md's 3-tier scale
    # feasible: false with the blocker(s) lacking alternatives named in the report text
    # aws_transform_applicability: source/target versions and automation scope when
    #   AWS Transform for .NET applies (recommendation only — execution is post-gate); null otherwise
    # null only when the path itself is not presented (mode: null or not_applicable)
```

**Invariants:**

- `mode` follows the [decision table](#presentation-decision-table) exactly — the five inputs determine it; no discretion.
- `mode: not_applicable` ⇒ `blocking_dependencies` is non-empty and every entry is a reported must-fix blocker.
- `mode: option | variant` ⇒ compute options (both A and B, three items each) appear in the report text.
- `base_image_policy` XOR (`base_image_undetermined_items` non-empty) whenever the path is presented.
- The recommendation block from [scoring-and-recommendation.md](scoring-and-recommendation.md) is never mutated by this submodule — `variant` mode in particular leaves it untouched.

---

## Output Schema

This module produces the `replatform_path` block — the source data for the report's "Replatform path details" section. Hold it in conversation context; the assessment phase writes no intermediate files. The `windows_container_path` block defined in [Windows_Container_Path Output Block](#windows_container_path-output-block) is carried alongside this block whenever a .NET Framework detection exists.

```yaml
replatform_path:
  target_compute_model: ecs_on_ec2   # ALWAYS stated explicitly; never another model here
  static_configuration:
    desired_task_count:
      policy: string                 # parity-with-current derivation, or the user-input request
      current_evidence: string | null  # deployment-config evidence, when available
    capacity_plan:
      basis: expected_peak_load      # never average load — no autoscaling absorbs bursts
      derivation_policy: string      # footprint x task count -> instances + N+1 headroom, >= 2 AZs
      delegation_note: string        # REQUIRED: instance-type selection & sizing -> ecs-architect
    operational_procedures:
      kept: [{procedure: string, grounds: string}]
      changed: [{procedure: string, replacement: string, grounds: string}]
      needs_confirmation: [string]   # items unclassifiable from evidence
  containerization_policy:
    base_image: {policy: string, grounds: string}       # from the detected-stack table
    app_server_bundling: {bundle: bool | deferred, rationale: string}
    config_intake:
      - {artifact: string, method: bake_into_image | environment_variables | efs | ssm_parameter_store,
         rationale: string}
    generic: bool                    # true when undetermined items limited the policy
    limitations: [string]            # REQUIRED when generic: the undetermined items named
  must_fix_handling:                 # EVERY must_fix blocker appears in exactly one list
    addressed: [{blocker_id: string, minimal_remediation: string}]
    unresolved: [{blocker_id: string, reason: string}]  # user-resolution items; path never suppressed
  local_writes:
    detected: bool
    mappings:                        # required when detected — one entry PER write target
      - {write_target: string, classification: persistent | temporary,
         treatment: string, evidence: string, unconfirmed: bool}
    not_needed_statement: string | null   # required when NOT detected: statement + grounds
  session_handling:
    in_process_session_detected: bool
    sticky_sessions: {presented: bool, mechanism: string, constraint: string} | null
                                     # constraint (session loss on task stop/replacement) is
                                     # REQUIRED whenever presented — never the remedy alone
  code_change_free: true             # invariant: the no-code-change audit passed; the ONLY
                                     # code changes presented are must_fix_handling.addressed
```

**Reporting invariants:**

- `target_compute_model` is always `ecs_on_ec2` and always stated in the report text.
- All three `static_configuration` elements and all three `containerization_policy` items are present in every output — none is skippable.
- Every `must_fix` blocker from the `blockers` block appears in exactly one of `addressed` / `unresolved`; a non-empty `unresolved` list never suppresses or truncates the rest of the block.
- `local_writes` has `mappings` (one per detected write target) XOR `not_needed_statement` — exactly one of the two, matching `detected`.
- `session_handling.sticky_sessions.constraint` is non-empty whenever `presented` is true.
- No evidence entry or description contains any part of a credential value.

---

## Edge Cases

### Undetermined language, framework, or application server

Present the generic containerization policy grounded only in what WAS determined, set `generic: true`, and name each undetermined item in `limitations` with the statement that the policy is limited because of it. The policy section is never skipped. See [Containerization Policy](#containerization-policy).

### must_fix blockers with no presentable remediation

List each as an unresolved item with the reason no remediation can be offered, and present the complete Replatform path anyway — unresolved items are carried visibly, never used to suppress the presentation. See [Must-Fix Blocker Handling](#must-fix-blocker-handling).

### Zero blockers

The path is pure containerization work: `must_fix_handling` has two empty lists (with the explicit absence statement carried from blocker detection), `local_writes.not_needed_statement` and the no-session statement apply per their sections. Explicit statements still appear — absence is reported, not implied.

### Write target with undeterminable persistence

Classify as **persistent** (fail-safe), mark `unconfirmed: true`, and note that the user should confirm whether the data is regenerable before finalizing the mount layout. Never default to temporary on missing evidence.

### .NET Framework detected

The base-image row and the compute-option presentation defer to the [Windows_Container_Path](#windows_container_path) section (its decision table governs whether it appears as an option, a variant, or not at all). The rest of this path — static template, must-fix handling, writes, sessions — applies unchanged.

### .NET Framework detected but no Fit_Score

The decision table's score conditions (rows 3–4) cannot be evaluated without a Fit_Score. The Windows-API-blocker arm of row 3 still fires on its own when such blockers exist. With zero Windows-specific API blockers and no score, present the path as an **option** (there is no standing recommendation for a variant to defer to — the no-score case presents both strategies in parallel), and note that the score condition was not evaluable. Row 2 (`not_applicable`) keeps its absolute precedence regardless.

### Grey zone / no Fit_Score

The Replatform path is presented **regardless** of the recommendation outcome — firm Rearchitect, firm Replatform, grey zone, or no score at all (the report always carries both strategies). Confidence notes from the recommendation carry through; this module does not re-judge confidence.

### User asks for the Dockerfile files or environment IaC

During the assessment, artifact illustrations are code blocks inside the Modernization_Report only — no files are created, and no Terraform/CloudFormation/CDK appears. Actual Containerization_Artifact generation and environment construction belong to the execution modules behind the Execution_Gate. This path's environment IaC is **not** delegated: `ecs-build` generates `awsvpc` task definitions and capacity-provider services exclusively and carries no `bridge`, dynamic-host-port, or ALB `stickiness` knowledge, so [replatform-environment-build.md](replatform-environment-build.md) generates it inside this skill. Only the Rearchitect compute models hand off to `ecs-build` by name.

### User asks for concrete sizing values

Present the derivation policies (task count parity, peak-based instance arithmetic, N+1 headroom) with the current-environment inputs named, and delegate instance-type selection, task sizing numbers, and network design to `ecs-architect` by name. Do not produce design values "just this once".

### Partial analysis

Derive the path from the readable evidence as usual; the partial-analysis state propagates to the report's incomplete-analysis section. A policy element whose decisive evidence fell inside excluded paths is presented as needs-confirmation or generic, not guessed.

---

## Sources

- Amazon ECS launch types (EC2 launch type characteristics): https://docs.aws.amazon.com/AmazonECS/latest/developerguide/launch_types.html
- Amazon ECS services and desired count (service scheduler, `desiredCount`): https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs_services.html
- Amazon ECS capacity for the EC2 launch type (container instances, cluster capacity): https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-capacity.html
- Amazon EFS volumes with ECS (mounting shared persistent storage into tasks): https://docs.aws.amazon.com/AmazonECS/latest/developerguide/efs-volumes.html
- Using data volumes in ECS tasks (bind mounts, ephemeral storage): https://docs.aws.amazon.com/AmazonECS/latest/developerguide/using_data_volumes.html
- Passing sensitive data to a container (SSM Parameter Store / Secrets Manager injection): https://docs.aws.amazon.com/AmazonECS/latest/developerguide/specifying-sensitive-data.html
- ALB sticky sessions (duration-based and application-based stickiness, session-loss semantics): https://docs.aws.amazon.com/elasticloadbalancing/latest/application/sticky-sessions.html
- Task placement constraints (confining tasks to designated instances — licensing remediation): https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-placement-constraints.html
- Amazon ECS scheduled tasks (recreating host cron jobs): https://docs.aws.amazon.com/AmazonECS/latest/developerguide/scheduled_tasks.html
- Using the awslogs log driver (container log collection replacing host log files): https://docs.aws.amazon.com/AmazonECS/latest/developerguide/using_awslogs.html
- Docker Official Images — Tomcat: https://hub.docker.com/_/tomcat , Eclipse Temurin: https://hub.docker.com/_/eclipse-temurin
- WebSphere traditional container images (build model, properties-file configuration, ICR; UBI 8 base, no authentication or pull rate limits): https://github.com/WASdev/ci.docker.websphere-traditional
- Oracle WebLogic Server container images: https://github.com/oracle/docker-images/tree/main/OracleWebLogic
- Running WebSphere Application Server in a container (ILAN license for entitled customers): https://www.ibm.com/docs/en/was/9.0.5?topic=cloud-running-websphere-application-server-in-container
- Liberty container images (`icr.io/appcafe/websphere-liberty`, `icr.io/appcafe/open-liberty`): https://www.ibm.com/docs/en/was-liberty/base?topic=images-liberty-container
- Licensing for WebSphere Application Server Liberty (traditional WAS entitlement includes Liberty entitlement): https://www.ibm.com/docs/en/was-liberty/base?topic=overview-licensing-liberty
- IBM Cloud Transformation Advisor (tWAS application assessment): https://www.ibm.com/docs/en/cta — its generated migration artifacts target Liberty, not tWAS: https://www.ibm.com/docs/en/cta?topic=migration-artifacts
- wsadmin properties-file-based configuration management: https://www.ibm.com/docs/en/was/9.0.5?topic=wsadmin-using-properties-files-manage-system-configuration , extracting properties files (`extractConfigProperties`): https://www.ibm.com/docs/en/was/9.0.5?topic=configuration-extracting-properties-files-using-wsadmin-scripting
- .NET container images (`mcr.microsoft.com/dotnet/aspnet`): https://learn.microsoft.com/en-us/dotnet/core/docker/container-images
- Windows containers on Fargate considerations (supported Windows Server versions, AWS-managed licensing, unsupported features): https://docs.aws.amazon.com/AmazonECS/latest/developerguide/windows-considerations.html
- Amazon ECS-optimized Windows AMIs (EC2 Windows container instances, considerations): https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-optimized_windows_AMI.html
- Amazon ECS-optimized Windows AMI versions (2025/2022/2019/2016 lineup): https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-windows-ami-versions.html
- ECS-optimized Windows Server 2025 AMIs announcement: https://aws.amazon.com/about-aws/whats-new/2025/07/aws-availability-ecs-optimized-windows-server-2025-amis/
- Task definition differences for Windows on EC2: https://docs.aws.amazon.com/AmazonECS/latest/developerguide/windows_task_definitions.html
- Windows container version compatibility (host/image version matching under process isolation): https://learn.microsoft.com/en-us/virtualization/windowscontainers/deploy-containers/version-compatibility
- FSx for Windows File Server volumes with ECS (persistent SMB storage for Windows tasks, EC2 launch type): https://docs.aws.amazon.com/AmazonECS/latest/developerguide/wfsx-volumes.html
- .NET Framework Docker images (`mcr.microsoft.com/dotnet/framework/*` — aspnet/runtime, 3.5/4.8, Server Core only): https://github.com/microsoft/dotnet-framework-docker
- Microsoft licensing on AWS (license-included vs BYOL): https://aws.amazon.com/windows/resources/licensing/
- AWS Fargate pricing (Windows OS license fee component): https://aws.amazon.com/fargate/pricing/
- AWS Transform for .NET (porting coverage: sources, targets, project types): https://docs.aws.amazon.com/transform/latest/userguide/dotnet.html
- AWS Prescriptive Guidance — migration strategies (the replatform "lift-and-reshape" definition): https://docs.aws.amazon.com/prescriptive-guidance/latest/strategy-migration/welcome.html
