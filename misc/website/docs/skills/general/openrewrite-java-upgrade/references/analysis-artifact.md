---
title: "Analysis artifact"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/openrewrite-java-upgrade/references/analysis-artifact.md
format: md
---

:::info[Source]
This page is generated from [skills/openrewrite-java-upgrade/references/analysis-artifact.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/openrewrite-java-upgrade/references/analysis-artifact.md). Edit the source, not this page.
:::

# Analysis artifact

Phase 1 produces this artifact before any code changes. Its job is to state, from the real dependency graph and the real Dockerfiles, what the upgrade will touch and which Phase 2 fixes apply. Read facts from the resolved tree and the pom, not from the framework version, because the native libraries and the TLS provider are almost always transitive.

## What to inspect and how

| Field | How to read it |
|-------|----------------|
| Current JDK | `<java.version>` in the parent pom (and compiler `source`/`target`). |
| Current Spring Boot | version on `spring-boot-starter-parent`. |
| Target | JDK 21, Spring Boot 3.3.x (the reference run landed 3.3.13). |
| Dependency tree | `mvn dependency:tree -DoutputFile=deptree-before.txt` (never `-q > file`, which empties it). |
| Native libs | `grep -Ei 'netty-tcnative|snappy-java|zstd-jni|kafka-clients|netty-transport-native-epoll' deptree-before.txt` plus their versions and `<scope>`. For each, note whether the version is BOM-managed or set by an explicit pin / `<properties>` value: property-pinned native libs will NOT move during the upgrade and keep their original arm64 risk (see gotcha 5). |
| TLS path | `grep -RniE 'SslProvider\.OPENSSL|SslContextBuilder|COMPRESSION_TYPE_CONFIG' src/ pom.xml src/main/resources`. No `SslProvider.OPENSSL` usage means JSSE, so tcnative is off the request path. |
| Base image | `find . -iname 'Dockerfile*' -exec grep -H 'FROM ' {} +`. A tag containing `alpine` is musl; otherwise glibc. |
| Reactive vs servlet | per module, `spring-boot-starter-webflux` (reactive) vs `spring-boot-starter-web` (servlet). |

## The three verdicts that drive the recommendation

1. **TLS path**: OpenSSL/tcnative (native, on the request path) vs JSSE (pure Java, tcnative N/A).
2. **Kafka compression**: snappy or zstd configured (native, on the path) vs none/gzip/lz4 (native N/A).
3. **Base image**: musl/Alpine (unsafe for live native libs on arm64) vs glibc (safe).

If all three native surfaces are N/A and the base is already glibc, the app needs only the version bump plus bcpkix if it calls `SelfSignedCertificate()` on JDK 21 (that fix is pure-Java and applies regardless of native surfaces or base image); skip the native-library fixes.

## Template

```
# OpenRewrite upgrade analysis: <app name>

## Current state
- JDK: <e.g. 11>
- Spring Boot: <e.g. 2.7.18>
- Modules: <count and layering, e.g. 6 (common + 5 services), experience/process/system>
- Base image(s): <FROM lines> -> <glibc | musl/Alpine>
- Reactive modules: <list of WebFlux modules> | Servlet modules: <list>

## Target state
- JDK: 21
- Spring Boot: 3.3.x

## Native-library footprint
| Library | Present | Version | Scope | On request path? |
|---------|---------|---------|-------|------------------|
| netty-tcnative-boringssl-static | <y/n> | <ver> | <scope> | <yes if SslProvider.OPENSSL used, else N/A> |
| netty-transport-native-epoll | <y/n> | <ver> | | classifiers: <linux-x86_64 / linux-aarch_64> |
| snappy-java | <y/n> | <ver> | | <yes if snappy codec configured> |
| zstd-jni | <y/n> | <ver> | | <yes if zstd codec configured> |
| bcpkix/bcprov | <y/n> | <ver> | <scope> | needed if SelfSignedCertificate on JDK 21 |

Version source (per native lib): <BOM-managed | property-pinned>. Property-pinned libs will not move during the upgrade.

## Verdicts
- TLS path: <OpenSSL-tcnative | JSSE>
- Kafka compression: <snappy | zstd | none/gzip/lz4>
- Base image: <musl | glibc>

## Recommended path
- <version bump only | version bump + strip web starter + bcpkix runtime + glibc base swap + native gate>
- Fixes that apply: <list>
- Fixes that are N/A here and why: <list>
```

The artifact is a deliverable in its own right. Save it as a file (for example `analysis-<app>.md`) so it can be attached to a migration runbook rather than living only in a chat transcript.
