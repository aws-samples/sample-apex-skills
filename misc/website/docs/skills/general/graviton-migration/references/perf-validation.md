---
title: "Post-Cutover Performance Validation & C/C++ Arch Flags"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/graviton-migration/references/perf-validation.md
format: md
---

:::info[Source]
This page is generated from [skills/graviton-migration/references/perf-validation.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/graviton-migration/references/perf-validation.md). Edit the source, not this page.
:::

# Post-Cutover Performance Validation & C/C++ Arch Flags

> **Part of:** [graviton-migration](../)

Getting a workload to *run* on arm64 is not the same as getting it to run *well*. The [dependency-floor scanner](scanner-workflow) and [multi-arch pipeline](multi-arch-pipelines) prove a build exists and starts on Graviton; this reference covers the step after that — measuring real performance against your SLO, and (for C/C++) picking the compiler flags that actually let Graviton earn its price/performance. Do the measurement with the user's real workload; never sign off a cutover on a synthetic score. Generate flag guidance from the tables here — do not recite compiler versions from memory, they drift and have been wrong before.

## Contents

- [Runs vs. runs well](#runs-vs-runs-well)
- [No SMT: benchmark to max sustainable load](#no-smt-benchmark-to-max-sustainable-load)
- [Tooling](#tooling)
- [C/C++ architecture flags](#cc-architecture-flags)
- [Signed vs. unsigned char](#signed-vs-unsigned-char)
- [SSE/AVX intrinsics → NEON](#sseavx-intrinsics--neon)
- [Lower-priority items](#lower-priority-items)

---

## Runs vs. runs well

A green scanner result — every dependency has an arm64 build, the image boots, health checks pass — proves only that the workload *runs*. Performance tuning is a separate, later activity. Treat these as two distinct gates: **"builds and runs on arm64"** (the scanner/pipeline gate) and **"meets or beats its SLO on Graviton at acceptable cost"** (this gate). A workload can clear the first and still need flag or config work to clear the second. Keep them separate in the migration plan so a passing dependency check is never mistaken for a passing performance check.

## No SMT: benchmark to max sustainable load

The single biggest measurement difference on Graviton: **every vCPU maps to a physical core, and there is no Simultaneous Multi-Threading (SMT / hyperthreading).** On a typical x86 instance two vCPUs share one physical core; on Graviton each vCPU *is* a core. This usually gives Graviton more linear, predictable scaling — but it means you cannot compare instance types on vCPU count alone.

The AWS Graviton transition guide's **Step 6 – Performance testing** prescribes the method: with a fully functional application, **fully load both the x86 and the arm64 instance types to find the maximum sustainable load** — the point just before latency or error rate exceeds your acceptable bounds — and compare *that*, not a fixed-RPS snapshot. For horizontally scalable, CPU-bound, multi-threaded workloads, Graviton often sustains a significantly higher transaction rate before latency degrades.

A concrete follow-on: if you run EC2 Auto Scaling (or CloudWatch-driven scaling generally), you **may be able to raise the CloudWatch alarm threshold values** that trigger scale-out, because each Graviton instance carries more real load before saturating. That can reduce the instance count needed to serve a given demand — a direct cost win that only shows up once you've measured max sustainable load rather than assuming vCPU parity.

Source: AWS Graviton Getting Started, `transition-guide.md`, Step 6 — Performance testing.

## Tooling

Measure with tools that read your real production code under a production-like load. In rough order of reach:

> **Host-execution guardrail:** `aperf record`, `perf record`, and sanitizer-built binaries all run *on* a live instance — these are host-level executions that must be confirmed with the user and run against a named/identified target host (never silently), consistent with the skill's host-execution interaction rule.

- **AWS APerf** ([github.com/aws/aperf](https://github.com/aws/aperf)) — a system-wide performance data collector and reporter built for exactly this kind of x86-vs-arm64 comparison. Run `aperf record` on each instance while it's under load, then `aperf report` to generate a browsable HTML report; collect on both architectures and diff the reports.
- **Linux `perf` + FlameGraphs** — `perf record` / `perf script` piped through Brendan Gregg's [FlameGraph](https://github.com/brendangregg/FlameGraph) (`stackcollapse-perf.pl | flamegraph.pl`) to find hot paths that differ between architectures.
- **Sanitizers** — the compiler may lay out code and data slightly differently on Graviton, so rebuild and run with `-fsanitize=address -fsanitize=undefined` (add to `CFLAGS` and `LDFLAGS`) to catch latent memory/UB bugs that x86 happened to tolerate.

The governing rule from the AWS Performance Runbook: **"No synthetic benchmark is a substitute for your actual production code."** The best benchmark is your production application under a load that approximates production.

## C/C++ architecture flags

On arm64, `-mcpu=` sets both the target architecture and the tuning; prefer it over `-march` when building for one specific CPU. To target **all current Graviton generations** (Graviton2 through Graviton5) with one binary, use **`-march=armv8.2-a`** — code built for a newer generation may not run on an older one, so pick the oldest generation you deploy to. Two different version numbers get conflated here: the **`-march=armv8.2-a` flag itself has been accepted since GCC 7 (2017) and Clang ~4–5**, whereas GCC 9 / Clang 10+ is AWS's recommended **Graviton2 tuning floor** (the `-mcpu=neoverse-n1` era guidance), *not* the minimum needed to compile for armv8.2-a. So the flag compiles on much older toolchains; the GCC 9+/Clang 10+ numbers are a practical tuning recommendation, not a hard flag-support requirement.

The version floors in the table below are a **verified-as-of-2026-08-05 snapshot** (cross-checked against the live GCC per-release changes pages and the AWS Graviton `c-c++.md` guide) — they are the one place a concrete version *is* given, precisely because they were verified against source, not recited from memory. Treat them like every other floor in this skill: **re-verify live** before you sign off, since toolchain support drifts. This is the reconciliation of the "don't recite versions from memory" rule above: cite *these* (sourced) numbers, not remembered ones, and confirm them current.

| Flag | Purpose | GCC floor | LLVM/Clang floor |
|------|---------|-----------|------------------|
| `-march=armv8.2-a` | balanced, runs on all current Graviton (G2–G5) | GCC 7 (flag); GCC 9+ = AWS G2 tuning floor | Clang/LLVM ~4–5 (flag); 10+ = AWS G2 tuning floor |
| `-mcpu=neoverse-v1` | perf-tuned for Graviton3(E) | GCC 11 | Clang/LLVM 12 (accepted); 14+ = AWS-recommended for tuning |
| `-mcpu=neoverse-512tvb` | balanced tuning across Graviton3/4/5 | GCC 11 | Clang/LLVM 14+ |
| `-mcpu=neoverse-v2` | perf-tuned for Graviton4 | GCC 13 | Clang/LLVM 16+ |
| `-moutline-atomics` | runtime LSE-atomics detection (safe on old + new cores) | GCC 10 (backported to GCC 9.4) | Clang/LLVM 12 |

Notes:
- **Generation → Neoverse core:** Graviton2 = Neoverse-N1, Graviton3(E) = Neoverse-V1, Graviton4 = Neoverse-V2, Graviton5 = Neoverse-V3. `-mcpu=neoverse-512tvb` is the AWS-recommended *balanced* flag for Graviton3 and later; if your compiler doesn't know it, fall back to Graviton2 tuning.
- **`-mcpu=neoverse-v2`/`-v3`** were back-ported into the GCC-11 shipped with Amazon Linux 2023, so AL2023's `gcc` accepts them despite the upstream GCC 13 floor.
- **`-moutline-atomics`** lets one binary use fast LSE atomics on cores that have them and fall back on cores that don't — the right choice when you must support a broad range of arm64 targets from a single build.
- **SVE auto-vectorization:** the AWS Graviton guide requires **GCC 11+, Clang/LLVM 14+, and a 4.15+ kernel**. (Upstream GCC has technically emitted SVE since GCC 8, but 11+ is the AWS-recommended Graviton floor; Amazon Linux 2 on a 4.14 kernel does *not* support SVE — move to a 5.4+ AL2 kernel.) Graviton3 and later support SVE; Graviton2 does not.

## Signed vs. unsigned char

The C standard leaves `char` signedness implementation-defined: **on x86 `char` is signed by default; on Arm it is unsigned.** Code that assumed signed `char` can break silently on Graviton. Fixes:

- Use explicitly-signed integer types — `uint8_t` / `int8_t` — wherever signedness matters, or
- Compile with **`-fsigned-char`** to force x86 semantics.
- For `getchar()`/EOF loops, store the result in an **`int`, not a `char`** — a `char` can't distinguish a valid `0xFF` byte from `EOF` (and on Arm's unsigned `char` the stored value is always 0–255, i.e. never negative, so `== EOF` can never be true — equivalently `!= EOF` is always true — and the loop never terminates). Check `feof(stdin)` / `ferror(stdin)` to disambiguate end-of-file from error.

## SSE/AVX intrinsics → NEON

If the code carries x86-specific SIMD intrinsics, don't hand-port everything up front. Drop in **`sse2neon.h`** ([github.com/DLTcollab/sse2neon](https://github.com/DLTcollab/sse2neon)), a header that reimplements SSE-family intrinsics — MMX, SSE through SSE4.2, and AES (as in `wmmintrin.h`) — on top of NEON with matching semantics. It does **not** cover AVX/AVX2/AVX-512; for AVX intrinsics reach for a different project (AvxToNeon, or SIMDe, which covers AVX). That gets a working arm64 build fast so you can profile it; then rewrite only the hot paths with native NEON intrinsics to shed the generic-translation overhead.

## Lower-priority items

- **64KB kernel page size (RHEL 8 family).** Most distros on Graviton use a 4KB page size. The **RHEL 8 family — RHEL 8.2+, AlmaLinux/Rocky 8.4+ — ships a 64KB kernel page size by default on aarch64.** The **RHEL 9 family (RHEL 9, CentOS Stream 9, AlmaLinux 9, Rocky 9) reverted to a 4KB default** on aarch64; 64KB there is available only as an opt-in via the `kernel-64k` package (source: RHEL 9.0 Release Notes — "Red Hat has selected a 4 KB page size … for the 64-bit ARM architecture in Red Hat Enterprise Linux 9"). (AWS's `os.md` still lists CentOS Stream 9 as 64KB as of 2026-08; that entry is stale — the RHEL 9.0 Release Notes confirm the 4KB default, and CentOS Stream 9 ships `CONFIG_ARM64_4K_PAGES=y`.) A 64KB page size can help TLB-bound workloads but can also raise memory footprint for many small allocations; verify with `getconf PAGESIZE` and re-measure RSS on these AMIs specifically. (Transparent-huge-page / large-folio behavior improved in recent kernels; confirm the exact kernel version live before quoting one.)
- **zlib-ng (use a recent release).** The stock `zlib` most distros ship has no Arm optimizations. zlib-ng has carried arm64 NEON + ARMv8 CRC32 code paths since its **1.x** line (those files date to 2016–2017); the **2.0.0 (2021)** release was its first stable release, not the arm64 introduction. Practically, just build against a current release (the **2.x** line) rather than pinning to a specific version — and verify the current version at migration time. For compression-heavy workloads, use **[zlib-ng](https://github.com/zlib-ng/zlib-ng)** (zlib-compatible API), which is reported to outperform the older zlib-cloudflare fork on Graviton (not independently benchmarked here — measure your own workload).
