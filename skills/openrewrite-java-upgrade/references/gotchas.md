# Settled fixes (do not re-derive)

These are the things OpenRewrite gets wrong or cannot see, each settled empirically in the reference migration. The compile stays green through most of them, which is exactly why they are dangerous: the failure shows up at runtime, in the cluster, not in the build. Apply the ones the Phase 1 analysis says are live.

## 1. Strip the spurious spring-boot-starter-web

**What happens.** The transform injects `spring-boot-starter-web` into modules, including reactive (WebFlux) ones where it does not belong. It brings in embedded Tomcat. The symptom depends on the scope OpenRewrite injects it at, and both have been seen:
- **Compile/runtime scope**: Tomcat ends up in the fat jar and starts a plaintext HTTP connector next to the Reactor Netty server doing OpenSSL TLS. Clients hitting the TLS port get `NotSslRecordException`, or the wrong server answers. This is what the reference migration hit in production.
- **Test scope**: it does not reach the fat jar, but it perturbs the reactive test application context (a WebFlux slice suddenly resolving a servlet web environment). Tests can flip or mask the reactive setup.

**Why it slips through.** The project still compiles either way; the break is a runtime TLS mismatch or a test-context change, not a compile error. So you only catch it by looking at the pom.

**Fix.** After `rewrite:run`, regardless of the scope it was injected at:
```bash
grep -Rn 'spring-boot-starter-web' */pom.xml
```
Delete the `spring-boot-starter-web` dependency from every module that is reactive (has `spring-boot-starter-webflux` and no legitimate servlet surface). Leave it in genuine servlet modules.

## 2. bcpkix must be runtime scope, not test

**What happens.** JDK 20 removed the type-unsafe `sun.security.x509` setters (JDK-8296143) that Netty's `io.netty.handler.ssl.util.SelfSignedCertificate` reflected on, so `new SelfSignedCertificate()` throws on JDK 20 and later, including 21 (and on an 11 to 21 hop): `OpenJdkSelfSignedCertGenerator not supported`. The fix is to put BouncyCastle on the path, which Netty will use instead.

**The scope trap.** Add `org.bouncycastle:bcpkix-jdk18on:1.78.1`. If you add it at `<scope>test</scope>` the unit tests go green (they have it) and then the fat jar does **not** include it, so the deployed service CrashLoops with `NoClassDefFoundError: org.bouncycastle.cert.X509v3CertificateBuilder`. It must be `<scope>runtime</scope>` so it is packaged into the jar.

```xml
<dependency>
  <groupId>org.bouncycastle</groupId>
  <artifactId>bcpkix-jdk18on</artifactId>
  <version>1.78.1</version>
  <scope>runtime</scope>
</dependency>
```

**Architecture note.** This is a pure-Java defect. It crashes identically on x86 and arm64; it is not a Graviton issue. **N/A** if the app uses a real (non-self-signed) certificate.

## 3. glibc base image for live native libraries on arm64

**What happens.** If Phase 1 found live native libraries (netty-tcnative on the OpenSSL TLS path, or snappy/zstd for Kafka compression) and the base image is musl/Alpine, the arm64 image is unsafe:
- netty-tcnative-boringssl-static fails to link against musl.
- snappy-java and zstd-jni reference glibc-only symbols on aarch64 (`__strftime_l` for snappy, `__fprintf_chk` for zstd) that musl does not provide. On a musl/Alpine base the load fails outright, because musl resolves relocations eagerly at load (`Error relocating: ... symbol not found`). The subtler failure mode is a glibc base that is missing a needed symbol: glibc binds functions lazily, so the `.so` `dlopen`s cleanly and only crashes when a cold code path first calls it, meaning a smoke test can pass while a real workload later dies.

A Java-21 / Boot-3 upgrade alone does **not** make a musl image arm64-safe. This is the durable finding.

**Fix.** Move off Alpine to a glibc base:
- `amazoncorretto:21` (Amazon Linux 2023 under the hood, about 269 MB), or
- `gcr.io/distroless/java21-debian12` (about 108 MB, no shell, harder to debug live).

Both were all-green on the native gate in the reference run.

**Do not add `libxcrypt-compat` (unless the app's own tcnative genuinely needs it).** `netty-tcnative-boringssl-static` links BoringSSL statically at every observed version (2.0.61, 2.0.69, 2.0.72), so its aarch64 `.so` has no `libcrypt.so.1` dependency at any of them and `libxcrypt-compat` is a no-op. The version bump did not create that no-op; it held at every version. The "needed on AL2023" line was a hypothesis, and it was found empirically false at 2.0.69. `libxcrypt-compat` matters only for an older or dynamically-linked, non-boringssl-static tcnative that actually references `libcrypt.so.1`. Check the app's own resolved tcnative version and its `.so` NEEDED list rather than assuming a single version number.

**cgroup note.** Moving from an Amazon Linux 2 base to Amazon Linux 2023 changes cgroups v1 to v2, which changes how the JVM reads container memory and CPU limits (ergonomics). Sanity-check heap and CPU sizing after the base swap; it is not a blocker but it can shift defaults.

## 4. Do not verify with a happy-path 200

Covered in full in `native-linkage-gate.md`. The one-line version: a `.so` that loads and answers one request is not proven sound; use `ldd -r` for unresolved symbols plus a real functional probe, and fail on either.

## 5. The upgrade may not move property-pinned native libraries

**What happens.** The Boot version bump moves everything the Spring Boot BOM manages. But native libraries are often pinned by an explicit `<version>` or a `<properties>` value in the pom rather than inherited from the BOM. Those do **not** move during the upgrade. In the reference app, `netty-tcnative` was BOM-managed and moved with the upgrade, but `snappy-java` (1.1.8.4) and `zstd-jni` (1.5.0-4) were property-pinned and stayed exactly where they were, carrying their original aarch64 glibc-symbol risk across the upgrade untouched.

**Why it matters.** It is easy to assume "upgraded to Boot 3.3, so the native stack is current." It is not. A stale property-pinned `snappy-java` or `zstd-jni` is precisely the library the arm64 linkage gate will fail on, and the version bump did nothing for it.

**Fix.** In Phase 1, record for each native library whether its version comes from the BOM or from an explicit pin (grep the pom for the artifactId and for a matching `<properties>` entry). After the upgrade, re-check: any native library still on its pre-upgrade version is property-pinned. Decide deliberately whether to bump it, and run it through the native-linkage gate regardless. Do not assume the framework upgrade moved it.

## 6. Boot 2 to 3 runtime config and Spring Security 5 to 6 (servlet apps; guidance, not lived-verified here)

The reference migration was a reactive service, so these were not exercised in the lived run. They are called out from Spring's own migration guidance, not from a green build, so treat them as designed guidance until you have run them on a servlet app. On a servlet or config-heavy app, two things bite after the version bump that the recipe does not fully cover:
- **Property renames and removals.** Boot 3 renames and removes many `application.yml` / `application.properties` keys. Add `org.springframework.boot:spring-boot-properties-migrator` as a temporary `runtime` dependency: it logs renamed and removed properties at startup so you can fix them, then remove it before shipping.
- **Spring Security 5 to 6.** `WebSecurityConfigurerAdapter` is removed; security config moves to a `SecurityFilterChain` bean and the lambda DSL. The Boot 3 recipe migrates much of this, but review the security config by hand on a servlet app.

## Quick applicability table

| Fix | Applies when | N/A when |
|-----|--------------|----------|
| Strip web starter | any reactive/WebFlux module | pure servlet app |
| bcpkix runtime scope | `new SelfSignedCertificate()` on JDK 21 | real certificate used |
| glibc base swap | live native libs + musl base | all native N/A, or already glibc |
| skip libxcrypt-compat | boringssl-static tcnative (any observed version) | non-boringssl-static tcnative referencing libcrypt.so.1 |
