---
title: "Native Dependency arm64 Floor Knowledge (Scan Layer 2)"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/graviton-migration/references/dependency-knowledge.md
format: md
---

:::info[Source]
This page is generated from [skills/graviton-migration/references/dependency-knowledge.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/graviton-migration/references/dependency-knowledge.md). Edit the source, not this page.
:::

# Native Dependency arm64 Floor Knowledge (Scan Layer 2)

> **Part of:** [graviton-migration](../)

This is **layer 2** of the Graviton migration scan: the manifest-parsing layer that
closes the gaps `migrate-ease` misses — Maven `<classifier>` mismatches and native
(JNI/FFI/CGO) dependencies whose arm64 support has a **minimum version floor**.

> **Verify at migration time (the floors below are a 2026-08-05 snapshot, not a live query).** Every floor below drifts as projects cut releases and
> deprecate runtimes. Treat this table as a starting hypothesis, not gospel. Re-check the
> package's release history (Maven Central, PyPI, crates.io, npm, project changelog) for
> the artifact you actually depend on before you sign off. Entries are labeled
> **conservative** (safe lower bound, real floor may be earlier) or **approximate**
> (reproduce/verify — not grounded in an authoritative KB) where that caveat applies.

## arm64 floor table

| Ecosystem / dependency | arm64 floor | Note |
|---|---|---|
| **.NET** runtime | **8 (LTS) minimum** | arm64 Linux works since .NET Core 3.0 (2019), but 3.0/3.1/5/6/7 are EOL; 10 is current LTS. "5+" is misleading — target a supported LTS. |
| **Python** (pip / wheels) | **pip ≥ 19.3**; target **3.11+** | pip ≥19.3 needed to resolve `manylinux2014`/aarch64 wheels; 3.9 is EOL (Oct 2025), so target 3.11+. |
| **Java** (JDK) | **JDK 8 min; recommend 11+/17+** | Corretto 11+ enables LSE atomics (better Graviton perf). Prefer 17+. |
| **netty-transport-native-epoll** (`linux-aarch64` / `linux-aarch_64`) | **arm64 epoll since 4.1.50.Final** | arm64 epoll natives first shipped at 4.1.50.Final as `linux-aarch64` (no underscore); the classifier spelling was **renamed to `linux-aarch_64` at 4.1.55.Final** — 4.1.55 is the rename point, not first arm64 support. Match both spellings; **verify current at migration time**. (migration-accelerator's KB says 4.1.46 — that predates arm64 epoll; see sources.) |
| **sqlite-jdbc** | glibc arm64 since ~3.20 (2017); **3.39.2.0** (Aug 2022) for musl/Alpine | *Approximate* — reproduce/verify the glibc-vs-musl split; not grounded in an authoritative KB. |
| **jna** | **≥ 5.5.0** | *Conservative* floor, not the introduction point. |
| **jnr-ffi** | **≥ 2.2.0** | *Conservative* floor, not the introduction point. |
| **snappy-java** | **1.1.2.2 (2016-03-29)** | `Linux/aarch64/libsnappyjava.so` has shipped since the early 1.1.x releases — the earliest release bundling it is **1.1.2.2 (2016-03-29)**; 1.1.7.8 merely rebuilt/enlarged it, so the practical floor is far earlier — *verify at release time* against Maven Central. |
| **lz4-java** | **≥ 1.4.0** | aarch64 native support around this release — *approximate; verify at release time*. |
| **Go** (toolchain) | **≥ 1.18** | Mature linux/arm64; earlier works but 1.18+ is the practical floor. |
| **Rust** (toolchain) | **≥ 1.57 (glibc); ~1.90 (musl)** | `aarch64-unknown-linux-gnu` is tier-1. Rust **1.57.0** enabled `+outline-atomics` by default for `aarch64-unknown-linux-gnu` (glibc) → good Graviton atomics; the musl target (`aarch64-unknown-linux-musl`) only picked it up much later (~1.90 (PR #144429)). Still, verify the current toolchain's target features (`rustc --print cfg -C target-cpu=…`) rather than pinning a version from memory. |
| **zlib-ng** | **use a current release** | arm64 NEON + ARMv8 CRC32 acceleration has been present since the 1.x line (those source paths date to 2016–2017); **2.0.0 (2021)** was the first stable release, not the arm64 introduction. No meaningful arm64-support floor — use a current release for Graviton perf. *Approximate — verify at release time.* |

## Layer-2 parsing procedure

Run per manifest found in the repo. For each native/classified dependency: (a) identify
arch intent, (b) compare declared version to the floor above, (c) emit a remediation.

1. **Java — `pom.xml`, `build.gradle(.kts)`**
   - Grep for `<classifier>` in `pom.xml` and `:classifier` / artifact suffixes in Gradle.
   - **Flag** any `linux-x86_64` / `linux-i386` / `windows-x86_64` / `osx-x86_64` classifier
     with **no matching arm64 classifier** for the same artifact. Match arm64 classifiers
     with the regex `linux-(aarch_?64|arm_64)` so both the pre-4.1.55 `linux-aarch64`
     (no underscore) and the `linux-aarch_64` / `linux-arm_64` spellings are recognized.
   - For netty-native, snappy-java, lz4-java, sqlite-jdbc, jna, jnr-ffi: compare `<version>`
     to the floor. **Remediation:** add/switch to the arm64 classifier and, if
     below floor, bump to ≥ floor. For netty, arm64 epoll exists since 4.1.50.Final — use
     the `linux-aarch64` classifier on 4.1.50–4.1.54 and `linux-aarch_64` on 4.1.55.Final+
     (match the version to the classifier spelling; don't bump solely for arm64 support).
   - Prefer multi-arch: shade both classifiers or use OS/arch-detection (`os-maven-plugin`).

2. **Python — `requirements.txt`, `Pipfile.lock`, `poetry.lock`, `pyproject.toml`**
   - Check for pinned `--platform`/`manylinux*_x86_64` wheel URLs or x86-only hashes.
   - Ensure build/runtime **pip ≥ 19.3** and interpreter **3.11+**.
   - **Remediation:** unpin arch-specific wheels; rely on `manylinux2014_aarch64`; rebuild
     the lockfile hashes on arm64 (or with `--platform manylinux2014_aarch64`).

3. **Node — `package.json`, `package-lock.json`, `yarn.lock`**
   - Flag native modules (node-gyp builds, prebuilt binaries): `sharp`, `bcrypt`,
     `node-sass`/`sass-embedded`, `canvas`, `better-sqlite3`. (Note: `@grpc/grpc-js`
     is pure-JS — no native binary; the genuinely-native gRPC package was the legacy,
     now-deprecated `grpc` package.)
   - Check `os`/`cpu` fields and `optionalDependencies` for `*-linux-arm64` / `*-linux-x64`
     platform packages. **Flag** an `x64`-only optional dep with no `arm64` sibling.
   - **Remediation:** ensure the `@scope/pkg-linux-arm64` platform package resolves;
     rebuild native addons on arm64 CI; bump to a version publishing arm64 prebuilds.

4. **.NET — `.csproj`, `packages.lock.json`, `runtimeconfig.json`**
   - Grep `RuntimeIdentifier(s)` / `<RuntimeIdentifier>` for `win-x64`/`linux-x64` with no
     `linux-arm64`. Check `runtimes/` RID folders in restored native NuGet packages.
   - Confirm `TargetFramework` maps to a supported LTS (net8.0+).
   - **Remediation:** add `linux-arm64` to `RuntimeIdentifiers`; verify each native NuGet
     ships a `runtimes/linux-arm64/native/*` payload; retarget to net8.0+.

5. **Ruby — `Gemfile.lock`**
   - Read the `PLATFORMS` stanza. **Flag** `x86_64-linux` (or `x86_64-linux-musl`) present
     with **no `aarch64-linux` / `arm64-linux`**. Watch native-ext gems: `nokogiri`,
     `sassc`, `ffi`, `grpc`, `sqlite3`, `google-protobuf`.
   - **Remediation:** `bundle lock --add-platform aarch64-linux` (and `-musl` for Alpine);
     bump native gems to versions publishing precompiled `aarch64-linux` gems.

## Sources

Floors were cross-referenced against two public projects and then live-verified where
noted. The **`awslabs/migration-accelerator-graviton`** project ships a native-dependency
knowledge base (its KB lists netty epoll at 4.1.46, which predates arm64 epoll support —
corrected here via a Maven Central check: arm64 epoll first shipped at 4.1.50.Final as
`linux-aarch64`, and the classifier was renamed to `linux-aarch_64` at 4.1.55.Final). The **ARM Ecosystem
Dashboard** (Arm's community project tracking arm64 support status across popular
open-source packages) informed the runtime/toolchain floors (.NET, Python, Go, Rust) and
the JNI/FFI library entries. Neither project's data files are vendored here; consult them
directly, and re-verify against the upstream package's own release history at migration time.
