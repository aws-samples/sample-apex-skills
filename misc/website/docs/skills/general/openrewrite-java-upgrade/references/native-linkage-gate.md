---
title: "Native-linkage gate (ELF gate v2)"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/openrewrite-java-upgrade/references/native-linkage-gate.md
format: md
---

:::info[Source]
This page is generated from [skills/openrewrite-java-upgrade/references/native-linkage-gate.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/openrewrite-java-upgrade/references/native-linkage-gate.md). Edit the source, not this page.
:::

# Native-linkage gate (ELF gate v2)

The purpose of this gate is to catch native libraries that load but are not actually sound on the target architecture. A functional probe that returns 200 is not sufficient. On a glibc base a wrong-arch or under-linked `.so` can `dlopen` successfully and then crash when a cold code path first calls an unresolved symbol, because glibc binds function symbols lazily (on first call). On a musl base the failure surfaces instead at load time (`Error relocating: ... symbol not found`), because musl resolves all relocations eagerly. Either way a happy-path probe is not proof. The gate fails if **either** the link check or the functional probe fails.

## The two checks

### 1. Full-relocation link check

Resolve every symbol in each bundled `.so`, not just load it.

- **glibc**: `ldd -r <lib>.so`. The `-r` performs relocation of both data and function symbols. Fail on any line containing `undefined symbol`. A happy `ldd` without `-r` only lists the shared-object dependencies and will not surface the unresolved-symbol fault.
- **musl**: the musl loader has no `-r` flag, and `/lib/ld-musl-<arch>.so.1 --list <lib>.so` lists library dependencies (the `NEEDED` entries), not individual symbols, so a glibc-only symbol like `__strftime_l` will never appear there. On musl the relocation failure surfaces at load time as an `Error relocating: ... symbol not found` line (musl resolves all relocations eagerly at load); fail the gate on any such line. To enumerate the glibc-only symbols a `.so` demands, read its undefined dynamic symbols directly: `readelf --dyn-syms <lib>.so | grep UND` (or `nm -D <lib>.so | grep ' U '`).

`NEEDED` (from `readelf -d <lib>.so` or the musl loader `--list`) shows library dependencies, not symbols; use it to see which shared objects a `.so` pulls in, not which symbols it needs resolved.

### 2. Functional probe

Exercise the library on a real path, not a health ping:
- TLS/tcnative: a real OpenSSL handshake (for example a `TlsHandshakeTest` that forces `SslProvider.OPENSSL`).
- Kafka compression: a produce/consume round-trip with the actual codec, `?codec=zstd` and `?codec=snappy`.

The reference run wired these as `/health/native`, `/health/tls`, and `/kafka/roundtrip?codec=zstd|snappy` endpoints and as JUnit tests (`NativeGatesTest`, `TlsHandshakeTest`, `KafkaCompressionTest`).

## Extracting the `.so` from a Boot 3 fat jar

The native libraries ship inside the application jar. To gate them you extract and inspect them. Two Boot-3 specifics matter:

1. The fat-jar loader launcher **moved** in Boot 3.2+: it is now `org.springframework.boot.loader.launch.PropertiesLauncher` (previously `org.springframework.boot.loader.PropertiesLauncher`). Scripts that reference the old package will break on Boot 3.2+.
2. Extract the jar and find the `.so` under the bundled dependency, then run the checks above. For example:
   ```bash
   unzip -o app.jar -d /tmp/app
   find /tmp/app -name '*.so'
   readelf -d /tmp/app/.../libnetty_tcnative_linux_aarch_64.so | grep NEEDED
   ldd -r /tmp/app/.../libnetty_tcnative_linux_aarch_64.so    # glibc image
   ```

## Running the gate inside the target image

Run the gate **in** the arm64 image you will ship, so you are testing the real base:

- **Corretto on AL2023**: `ldd` is present, but `find` is not by default. Install it first: `dnf install -y findutils`.
- **Distroless**: there is no shell, so you cannot exec into it. Audit out of band: `docker cp` the `.so` out (or copy it in a builder stage) and run `ldd -r` where a shell exists.

## Never verify under QEMU

Build and gate arm64 images on native arm64 runners. Emulation (QEMU/binfmt) can paper over exactly the linkage and instruction faults you are trying to catch, so an emulated pass is not evidence. Build each architecture natively. Assembling the per-arch builds into a multi-arch image (`docker manifest`, and pushing it to a registry) is the `graviton-migration` skill's job, not this one: this skill stops at a per-arch green build and a native-linkage verdict.

## Verdict format

Report per library:

```
netty-tcnative (aarch_64): ldd -r clean, TLS handshake OK  -> PASS
snappy-java   (aarch_64): ldd -r clean, zstd/snappy round-trip OK -> PASS
```

Any `undefined symbol` or any failed probe is a FAIL for that library, regardless of whether a smoke test passed.
