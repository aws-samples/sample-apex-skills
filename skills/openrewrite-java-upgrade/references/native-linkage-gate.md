# Native-linkage gate (ELF gate v2)

The purpose of this gate is to catch native libraries that load but are not actually sound on the target architecture. A functional probe that returns 200 is not sufficient: a musl-linked or wrong-arch `.so` can `dlopen` successfully and then crash when a cold code path first calls an unresolved symbol. The gate fails if **either** the link check or the functional probe fails.

## The two checks

### 1. Full-relocation link check

Resolve every symbol in each bundled `.so`, not just load it.

- **glibc**: `ldd -r <lib>.so`. The `-r` performs relocation of both data and function symbols. Fail on any line containing `undefined symbol`. A happy `ldd` without `-r` only lists the shared-object dependencies and will not surface the unresolved-symbol fault.
- **musl**: the musl loader has no `-r` flag. Use the loader directly to list what the object needs:
  `/lib/ld-musl-<arch>.so.1 --list <lib>.so`
  and inspect the `NEEDED` entries. On musl this is how you confirm whether the glibc-only symbols (for example `__strftime_l`, `__fprintf_chk`) are being demanded.

You can also read the declared needs with `readelf -d <lib>.so` (look at `NEEDED`) as a cross-check.

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

Build and gate arm64 images on native arm64 runners. Emulation (QEMU/binfmt) can paper over exactly the linkage and instruction faults you are trying to catch, so an emulated pass is not evidence. Build each architecture natively and, for a multi-arch image, assemble with `docker manifest create` / `docker manifest push` from the per-arch builds.

## Verdict format

Report per library:

```
netty-tcnative (aarch_64): ldd -r clean, TLS handshake OK  -> PASS
snappy-java   (aarch_64): ldd -r clean, zstd/snappy round-trip OK -> PASS
```

Any `undefined symbol` or any failed probe is a FAIL for that library, regardless of whether a smoke test passed.
