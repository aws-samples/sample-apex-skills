---
title: "openrewrite-java-upgrade"
description: "Analyze and upgrade a Java or Spring application to a modern JDK and Spring Boot line with OpenRewrite (Java 11 to 21, Spring Boot 2.7 to 3.3), then land a green build. Phase 1 emits an analysis artifact: current vs target JDK and Boot, base image (glibc vs musl/Alpine), the native-library footprint (netty-tcnative, snappy, zstd), and the TLS path read from the pom. Phase 2 runs the OpenRewrite recipe and applies the settled fixes: strip the spurious spring-boot-starter-web injected into WebFlux modules, put bcpkix at runtime scope, add BouncyCastle for the SelfSignedCertificate crashloop, move to a glibc base image for arm64 safety, and gate native libraries with 'ldd -r'. Use whenever someone wants to upgrade Java or Spring Boot, run OpenRewrite, modernize a Spring app, migrate Boot 2 to 3, move off Java 8/11 to Java 21, or debug a post-upgrade native-library or TLS crashloop. Maven only (not Gradle). Not for the arm64/Graviton node cutover itself (use graviton-migration) or general EKS work."
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/openrewrite-java-upgrade/SKILL.md
format: md
---

:::info[Source]
This page is generated from [skills/openrewrite-java-upgrade/SKILL.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/openrewrite-java-upgrade/SKILL.md). Edit the source, not this page.
:::


# OpenRewrite Java Upgrade

This skill takes a Java or Spring Boot application from an old JDK and framework line to a modern one, using OpenRewrite for the mechanical code transform and then repairing the small set of things the transform gets wrong or cannot see. The reference run behind it moved a 6-module Spring reactive service from Java 11 / Boot 2.7.18 to Java 21 / Boot 3.3.13 and landed a green build with tests passing.

The value is not "run OpenRewrite" (that is one command). The value is knowing, before you start, what in the application will break that OpenRewrite does not touch, and applying the exact fixes so the upgrade ends in a running service rather than a green compile that CrashLoops in the cluster. Those fixes are settled findings from a lived migration, not guesses. Encode them; do not re-derive them.

## Scope boundary

This skill owns the **application upgrade**: the JDK and Spring Boot version bump, the dependency and source transform, and the native-library and TLS fallout that the bump surfaces. It stops at a green build and a native-linkage verdict. It is **Maven only**: every command and the plugin block assume a Maven project. Gradle (the `rewrite-gradle-plugin`) is not covered here; the findings are portable but the invocation is Maven-specific.

It does **not** own the architecture cutover. Moving nodes to arm64/Graviton, Karpenter NodePool changes, multi-arch CI pipelines, and readiness scanning belong to the `graviton-migration` skill. When the app upgrade is done and the question becomes "now put it on arm64 nodes," route there. The two skills share one fact (glibc base images are the durable arm64 fix for these native libs), which is why it appears in both.

## Two phases

Always run Phase 1 before Phase 2. The analysis artifact is what tells you which of the Phase 2 fixes actually apply to this app. Skipping it means applying fixes blind or missing one that matters.

## Phase 1: Analyze

Produce an analysis artifact for the application. The point is to read the real dependency graph and the real Dockerfiles, not to assume from the framework version. Inspect against the resolved tree, because native libraries and the TLS provider are usually pulled transitively.

Run these against the project root:

- **Current JDK and Boot version**: read the `<java.version>` property and the `spring-boot-starter-parent` version from the parent pom.
- **Full dependency tree** (this is the substrate for everything else):
  `mvn dependency:tree -DoutputFile=deptree-before.txt`
  Do not use `-q > file`: the quiet flag empties the tree. Then:
  `grep -Ei 'netty-tcnative|snappy-java|zstd-jni|kafka-clients|netty-transport-native-epoll' deptree-before.txt`
- **TLS path** (JSSE vs OpenSSL/tcnative, read from source, not assumed):
  `grep -RniE 'SslProvider\.OPENSSL|SslContextBuilder|COMPRESSION_TYPE_CONFIG' src/ pom.xml src/main/resources`
  If nothing uses `SslProvider.OPENSSL`, the TLS path is JSSE and tcnative is not on the request path (its native gate is N/A even if the jar is present).
- **Base image, glibc vs musl**:
  `find . -iname 'Dockerfile*' -exec grep -H 'FROM ' {} +`
  Record the exact tag. Any tag containing `alpine` is musl. Everything else here (Corretto, Temurin non-alpine, distroless-debian) is glibc.
- **Reactive vs servlet**: `grep -Rn 'spring-boot-starter-webflux\|spring-boot-starter-web' */pom.xml`. Modules with webflux and no web are reactive; this matters for the spurious-web-starter fix in Phase 2.

Write the findings into the artifact template in `references/analysis-artifact.md`. The three verdicts that drive the recommendation are: TLS path (OPENSSL-tcnative vs JSSE), Kafka compression codec (snappy/zstd vs none/gzip/lz4), and base image (musl vs glibc). If all native surfaces are N/A and the base is already glibc, the app needs only the version bump plus bcpkix if it calls `SelfSignedCertificate()` on JDK 21 (that fix is pure-Java and applies regardless of native surfaces or base image); the native-library fixes below do not apply.

## Phase 2: Run the upgrade

### Wire the OpenRewrite plugin

Use these exact coordinates. They are the versions from the successful lived run, and they matter: see the version-drift warning below before copying anything from an existing pom.

- Plugin: `org.openrewrite.maven:rewrite-maven-plugin` **6.46.1**
- `org.openrewrite.recipe:rewrite-spring` **6.37.0**
- `org.openrewrite.recipe:rewrite-migrate-java` **3.42.0**
- `org.openrewrite.recipe:rewrite-recipe-bom` **3.37.0**, pinned **by value** inside the plugin `<dependencies>` block. An `<scope>import</scope>` BOM is illegal inside a plugin `<dependencies>` block, so you cannot import it the usual way; pin the recipe artifact versions directly.
- Active recipes (run all **three** together, in this order):
  1. `org.openrewrite.java.migrate.UpgradeToJava21`
  2. `org.openrewrite.java.spring.boot3.UpgradeSpringBoot_3_3`
  3. `org.openrewrite.java.migrate.jakarta.JakartaEE10`

Wire all three. `UpgradeSpringBoot_3_3` already transitively includes both `UpgradeToJava17` (Boot 3's Java floor) and `JakartaEE10` (via `UpgradeSpringFramework_6_0`), so on its own it lands the project at **Java 17** with the `javax` to `jakarta` migration already done. It does **not** include `UpgradeToJava21` (that recipe is nowhere in the Boot chain), so running the Boot recipe alone leaves you at 17, not 21. The one genuinely-required explicit add is therefore `UpgradeToJava21`, which carries you the rest of the way to 21. `JakartaEE10` is listed explicitly too, but only as a redundant-but-harmless (idempotent) belt-and-braces entry that keeps the wiring correct even on a servlet app; the Boot chain would run it anyway. `rewrite-migrate-java` provides `UpgradeToJava21` and `JakartaEE10`; `rewrite-spring` provides the Boot recipe.

The full plugin XML block is in `references/openrewrite-config.md`.

> **Version-drift warning (verified, important).** Kit poms in the wild, including the reference app, pin an **older** OpenRewrite stack (plugin 5.46.0, rewrite-spring 5.24.x, rewrite-migrate 2.29.x, recipe `UpgradeSpringBoot_3_2` or `_3_x`, sometimes with those recipes commented out), and superseded notes pin Boot 3.2.12. Do not copy those. The values above (6.x, `_3_3`, Boot 3.3.x) are the ones that produced a green build. Replace the stale plugin config; do not extend it. Separately, do not read a single post-upgrade tcnative version into the skill: the lived lane recorded `netty-tcnative` 2.0.69.Final and the guide pins 2.0.72.Final, so read the app's own resolved version rather than assuming one.

### Run the transform and fix the fallout

The loop is: baseline green, dry run, run, re-test on the new JDK, fix the two things the transform gets wrong.

1. Baseline on the old JDK so you know you started green:
   `mvn -q test`
2. Preview the changes: `mvn -U org.openrewrite.maven:rewrite-maven-plugin:dryRun`
3. Apply: `mvn org.openrewrite.maven:rewrite-maven-plugin:run`
4. Re-test on the target JDK: `mvn -q test`. This is where the two hand-fixes surface.
5. **Assert the compile target is really Java 21.** A green build is not proof: if the recipe only floored you at Java 17, the code still compiles and tests still pass on a JDK 21 runtime. Confirm the emitted bytecode is Java 21 (class-file major version **65**), not 17 (major 61):
   `javap -v -cp target/classes <AnyCompiledClass> | grep 'major version'`  (expect `major version: 65`)
   Also confirm the parent pom now sets `<java.version>21</java.version>`. If you see major version 61 / `java.version` 17, the `UpgradeToJava21` recipe was not active; fix the recipe wiring and re-run.

The settled fixes, each explained with the exact edit, are in `references/gotchas.md`. In short:

- **Strip the spurious `spring-boot-starter-web`.** OpenRewrite adds `spring-boot-starter-web` to reactive (WebFlux) modules. That drags in embedded Tomcat. If it lands at compile/runtime scope it starts a plaintext HTTP connector alongside the Reactor Netty TLS server and produces `NotSslRecordException` at runtime (the lived-run symptom); if it lands at test scope it perturbs the reactive test context instead. Either way it does not fail the compile, so you only catch it by looking. After `run`, `grep -Rn 'spring-boot-starter-web' */pom.xml` and delete it from any reactive module regardless of the scope it was injected at.
- **bcpkix at runtime scope, not test.** JDK 20 removed the type-unsafe `sun.security.x509` setters (JDK-8296143) behind Netty's `SelfSignedCertificate`, so `new SelfSignedCertificate()` throws on JDK 20 and later (including 21, and on an 11 to 21 hop) unless BouncyCastle is present. Add `org.bouncycastle:bcpkix-jdk18on:1.78.1`, but at `<scope>runtime</scope>`. At `test` scope it satisfies the unit tests and then is absent from the fat jar, so the deployed service CrashLoops with `NoClassDefFoundError: ...X509v3CertificateBuilder`. This is a pure-Java defect and is architecture-independent; it would crash the same way on x86. If the app uses a real certificate instead of a self-signed one, this fix is N/A.
- **glibc base image for native libraries on arm64.** If Phase 1 found live native libraries (tcnative on the OPENSSL path, or snappy/zstd for Kafka compression) and the base image is musl/Alpine, the arm64 image is unsafe: netty-tcnative fails to link against musl, and snappy and zstd reference glibc-only symbols on aarch64 (`__strftime_l`, `__fprintf_chk`) that musl does not provide, so on Alpine the load fails outright (musl relocates eagerly). The subtler failure is a glibc base that is missing a needed symbol: glibc binds functions lazily, so the `.so` dlopens cleanly and only crashes on a cold path, and a smoke test can pass while a real workload later dies. A Java-21 / Boot-3 upgrade alone does **not** fix this. Move to a glibc base: `amazoncorretto:21` (about 269 MB) or `gcr.io/distroless/java21-debian12` (about 108 MB, no shell). Do **not** add `libxcrypt-compat`: `netty-tcnative-boringssl-static` links BoringSSL statically at every observed version (2.0.61 through 2.0.72), so there is no `libcrypt.so.1` dependency at any of them and the package is a no-op. (The "needed on AL2023" line was a hypothesis, found empirically false at 2.0.69, not something that changed at a later version.) It matters only for an older or dynamically-linked, non-boringssl-static tcnative that references `libcrypt.so.1`; check the app's own resolved version.
- **Servlet or config-heavy apps (guidance, not lived-verified here).** The reference run was reactive, so these were not exercised in it. On a servlet or config-heavy app, Boot 2 to 3 also renames and removes `application.yml`/`.properties` keys and removes `WebSecurityConfigurerAdapter` (Spring Security 5 to 6). Add `spring-boot-properties-migrator` as a temporary `runtime` dependency to surface property changes, and review the security config by hand. See `references/gotchas.md`.

### Verify native linkage (the gate that matters)

A functional probe that returns 200 is not proof the native libraries are sound. On a glibc base a `.so` can `dlopen` successfully and then crash when a cold code path first hits an unresolved symbol, because glibc binds function symbols lazily; on a musl base the failure surfaces eagerly at load time (`Error relocating: ... symbol not found`). The real gate is a full-relocation link check plus a functional probe, and it fails if **either** fails.

For each bundled `.so`, resolve every symbol:
- glibc: `ldd -r <lib>.so` and fail on any `undefined symbol` line.
- musl: the musl loader resolves all relocations eagerly at load, so a missing glibc-only symbol fails as an `Error relocating: ... symbol not found` line; fail the gate on any such line. Note `/lib/ld-musl-<arch>.so.1 --list` shows `NEEDED` library dependencies, not individual symbols, so a symbol like `__strftime_l` never appears there; to enumerate demanded glibc-only symbols use `readelf --dyn-syms <lib>.so | grep UND` (or `nm -D <lib>.so | grep ' U '`).

Then run the functional probe (a real handshake or round-trip, e.g. an OpenSSL TLS handshake and a `zstd`/`snappy` Kafka round-trip). The details, including extracting the `.so` from a Boot 3 fat jar (the loader launcher moved to `org.springframework.boot.loader.launch.PropertiesLauncher` in Boot 3.2+) and the Corretto-on-AL2023 `dnf install -y findutils` prerequisite, are in `references/native-linkage-gate.md`.

Do not build arm64 images under QEMU emulation for this verification; build natively per architecture, because emulation can mask exactly the linkage faults you are checking for.

## Decision logic (which fixes apply)

- Base is musl/Alpine **and** native libraries are live -> swap to a glibc base (mandatory for arm64 safety).
- Base is musl/Alpine **and** all native surfaces N/A -> the musl base is tolerable for the JVM alone, but glibc is still the safer default.
- Any reactive/WebFlux module -> strip the injected `spring-boot-starter-web`.
- App calls `new SelfSignedCertificate()` on JDK 21 -> add bcpkix at runtime scope. Uses a real cert -> skip.
- boringssl-static tcnative (any observed version) -> `libxcrypt-compat` is a no-op; do not add it. Only a non-boringssl-static tcnative that references `libcrypt.so.1` needs it.

## Reporting

Emit two things:
1. The **analysis artifact** (Phase 1), saved as a file so it can be attached to the migration runbook.
2. A short **upgrade result**: baseline vs final JDK and Boot version, the observed class-file major version (65 = Java 21, the acceptance bar, not just a green build), modules and tests passing, which fixes were applied, and the native-linkage gate verdict per library.

Label anything you designed but did not execute as such. If you could not run the build (no toolchain, no registry egress), say the upgrade steps are designed-not-run and stop short of claiming a green build.

## References

- `references/analysis-artifact.md`: what to inspect and the artifact template.
- `references/openrewrite-config.md`: the exact plugin XML, versions, and recipe wiring, with the version-drift warning.
- `references/gotchas.md`: the settled fixes with the concrete pom edits and why each one bites.
- `references/native-linkage-gate.md`: the `ldd -r` gate, fat-jar `.so` extraction, glibc vs musl, and the no-QEMU rule.
