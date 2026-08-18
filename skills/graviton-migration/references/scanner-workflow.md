# Pre-Migration Scanning Workflow

> **Part of:** [graviton-migration](../SKILL.md)

This reference turns the Arm migration MCP into a repeatable pre-migration scan that produces a **per-workload readiness verdict** — clean, portable-with-changes, or blocked — grounded in evidence, not optimism. The core rule: **no single tool is the oracle.** Readiness is decided by **three co-equal input layers** plus a hard gate that refuses to call an under-scanned tree "clean."

## Contents

1. [Why three layers](#why-three-layers)
2. [The three input layers](#the-three-input-layers)
3. [The built-source gate (run this)](#the-built-source-gate-run-this)
4. [Interpret findings: blocker vs. warning vs. clean](#interpret-findings-blocker-vs-warning-vs-clean)
5. [Check every container base image for an arm64 variant](#check-every-container-base-image-for-an-arm64-variant)
6. [Choose a remediation pattern per finding](#choose-a-remediation-pattern-per-finding)
7. [Re-scan and emit a verdict](#re-scan-and-emit-a-verdict)

---

## Why three layers

The MCP's source scanner is **migrate-ease** ([github.com/migrate-ease/migrate-ease](https://github.com/migrate-ease/migrate-ease), Apache-2.0). It is good, but it has known blind spots (confirm against your scanner version), and it happily returns `"total_issue_count": 0` on a repo it never had enough to scan. The failure mode this workflow exists to prevent: a bare manifest repo (a lone `pom.xml`, no built code) scans "0 issues," and the agent reports **CLEAN**. That verdict is worthless — the scanner saw no compiled artifacts and no dependency contents. Treat a low finding count as a question, never an answer.

## The three input layers

Run **all three**. Layers 2 and 3 are **mandatory** — they are not optional backstops for layer 1, they are peers to it.

### Layer 1 — `migrate_ease_scan` via the MCP

Call the source scanner against the mounted workspace. It statically inspects the source tree. **Confirm the tool's real registered name and its supported languages from the MCP's `tools/list` — do not assume `migrate_ease_scan`, and do not assume the language set, which the server version can change.** (`arch` is a fixed migrate-ease set, not surfaced by `tools/list` — see below.) Key parameters include `scanner` (required, a supported language — the MCP exposes a subset of the underlying migrate-ease scanners and rejects unexposed values with `Unsupported scanner`), `arch`, `git_repo`, `output_format`, and `extra_args`. Note that the MCP tool schema types `scanner` and `arch` as free-form strings with no JSON-Schema enum, so their accepted *values* are validated at runtime (when the call reaches the wrapper), not by the schema — an unsupported scanner value fails at scan time with `Unsupported scanner`. The contract still rejects unknown *parameters*, though (`additionalProperties` is false), so a bad keyword like `path=` fails earlier, at call validation. **There is no `path` argument** (confirm the live schema via the MCP's `tools/list`, since the accepted parameters can change between image releases) — the scan target is the container's `/workspace` mount you set with `-v "$(pwd)":/workspace:ro`; passing `path=` is rejected as an unexpected keyword. Use **`arch=armv8-a`** (the default and the safe Graviton-readiness baseline): the underlying migrate-ease `--march` accepts a fixed set and any value outside it exits non-zero — notably `aarch64` is **rejected**. This set is not surfaced by `tools/list` (the schema types `arch` as a free-form string with no enum), so treat `armv8-a` as the known-good default; if a run rejects it, migrate-ease changed its `--march` options — check the error. A valid call is `{"scanner":"cpp","arch":"armv8-a"}` (no path arg). It returns a JSON payload with `returncode`, `parsed_results.issue_summary`, and a `workspace_listing`.

- **Genuinely catches:** `.S` assembly source, `-m64` and similar build flags (`BuildCommandIssue`), and x86 header includes (`xmmintrin.h`, `emmintrin.h`, `immintrin.h` → `IncompatibleHeaderFileIssue`).
- **Known blind spots (confirm against your scanner version) — do NOT trust a clean scan to cover these:**
  - Maven `<classifier>` tags (e.g. `<classifier>linux_amd64</classifier>`) pinning an x86-only native JAR — **not flagged at all**.
  - SSE/AVX intrinsics guarded by `#ifdef __x86_64__` — the guarded block is **skipped**; the identical unguarded code is flagged.
  - Off-list intrinsics: migrate-ease matches an enumerated pattern set, **not** a `_mm_.*` catch-all, so novel or renamed intrinsics slip through.
  - GCC inline-asm `cpuid` and similar hand-rolled asm probes.

Layer 1 is **never the sole oracle.** Its output is one input to the gate below, weighted equally with layers 2 and 3.

### Layer 2 — dependency-manifest parse (mandatory)

Parse the dependency manifests directly — this is where the `<classifier>` and native-package blind spots are caught, because layer 1 does not read them. This layer is owned by [dependency-knowledge.md](./dependency-knowledge.md); follow its per-ecosystem procedure (Maven/Gradle, pip/Poetry, npm, Go modules, Cargo). It **must run** on every workload, even when layer 1 returns zero.

### Layer 3 — binary / JAR ELF scan (mandatory)

Layer 1 does not open compiled artifacts; you must. The agent runs generic shell — no special tool needed:

1. Detect arch by ELF magic on **every regular file**, not by extension. An extension-filtered `find` both short-circuits (an `-exec … +` binds only to the branch after the last `-o`, so `.so/.a/.dll/.exe` never reach `file`) and misses extensionless binaries (a built Go `./app`). Let `file` read the magic on all files and keep the ELF lines:

   ```bash
   # Match ONLY the file(1) TYPE field (the text AFTER the colon), never the path --
   # otherwise 'SelfSignedCertificate.java', an "HTML document", or a directory named
   # '.../myelfdir/...' falsely match a bare 'ELF' grep. `:[^:]*\bELF\b` anchors on the
   # type section. The sed pattern re-anchors the same way, so a non-ELF line yields an
   # empty token and is dropped (not emitted with a blank arch).
   find "$T" -type f -exec file {} + | grep -E ':[^:]*\bELF\b' | while IFS= read -r line; do
     path="${line%%:*}"
     # arch token = the field after 'ELF <class> LSB <type>,' e.g. 'x86-64', 'ARM aarch64', 'Intel 80386'
     arch=$(printf '%s\n' "$line" | sed -n 's/^[^:]*:[^:]*\bELF\b[^,]*, \([^,]*\),.*/\1/p')
     [ -z "$arch" ] && continue   # non-ELF / unparsable line -> drop, never emit blank
     case "$arch" in
       *aarch64*|*AArch64*) echo "$path -> OK (arm64)";;
       *) echo "$path -> BLOCKER (non-aarch64: $arch)";;   # x86-64, Intel 80386, 32-bit ARM, etc.
     esac
   done
   ```

   Flag any line whose arch token is **not** `aarch64` (e.g. `x86-64`, `Intel 80386`, 32-bit `ARM`) as a blocker unless a matching arm64 build exists. Do **not** grep a bare `ELF` against the whole `file` line — that matches "elf" in filenames (`SelfSignedCertificate.java`), in directory names, and in type strings like "HTML document"; only the arch/type text after the colon is authoritative.
2. To confirm a single artifact directly: `readelf -h <file> | grep Machine` — `AArch64` is portable, `X86-64`/`Advanced Micro Devices X86-64` is a blocker unless an arm64 build exists.
3. **Recurse nested fat-JARs.** A Spring Boot / shaded JAR hides native libs under `BOOT-INF/lib/` and `WEB-INF/lib/`. Unzip each JAR to a temp dir, then unzip the inner JARs, and run steps 1–2 on every file inside. A pure-bytecode app can still ship an x86-only `.so` three levels deep.

## The built-source gate (run this)

This is an **imperative the agent MUST execute**, not advice. It decides whether layer 1's result is even admissible. It is a **heuristic backstop**, not proof of a build: its job is to refuse to call a possibly-unbuilt tree CLEAN. Gate on **genuine compiled output**, not an arbitrary file count (a `< N files` threshold false-STOPs on monorepos and thin modules) and not mere directory non-emptiness. Rule: **if layer 1 returned 0 findings AND no genuine compiled output was present in the scanned tree, the verdict is `INVALID` ("insufficient input — build first"), never `CLEAN`, and layers 2–3 are forced.** The gate **fails toward INVALID**: when it cannot positively confirm compiled output for the target, it does not emit CLEAN — the dangerous direction is a false `built=1` (→ false CLEAN), so detection is deliberately conservative.

A committed **wrapper jar** (`maven-wrapper.jar`/`gradle-wrapper.jar`/`*-wrapper.jar`), a **test-fixture `.so`** (under `test/`, `tests/`, `src/test/`, `testdata/`, a `*fixture*` path, etc.), and a **config-only `build/`** (e.g. zstd ships `build/` with ~81 cmake/meson/VS files) are **NOT** "built" — they are incidental committed files, so the gate prunes them before counting.

```bash
# usage: gate.sh <scanned_tree> <migrate_ease_finding_count>
TREE="$1"; FINDINGS="$2"; BUILT=0

# Fail CLOSED on a bad/empty finding count. An empty or non-numeric FINDINGS
# means the scan did not return a usable count -- treat as INVALID, never "clean".
# (Guard BEFORE any numeric comparison: `[ "$FINDINGS" -eq 0 ]` on ""/"err" errors out.)
if ! [[ "$FINDINGS" =~ ^[0-9]+$ ]]; then
  echo "VERDICT: INVALID (scan did not return a usable finding count -- build first / re-run)."
  exit 2
fi

# PRUNE incidental paths that ship committed NON-output files BEFORE counting anything:
# VCS metadata, the maven/gradle wrapper, test fixtures, examples, samples, AND vendored /
# third-party / dependency dirs (vendor, third_party, third-party, deps, .deps, lib, libs).
# Those last dirs hold FOREIGN/vendored binaries, not THIS tree's fresh build output, so a
# committed x86 .so under vendor/ or a .jar under lib/ must NOT satisfy the gate on its own.
prune_expr=( '(' -path '*/.git/*' -o -path '*/.mvn/*' \
  -o -path '*/test/*' -o -path '*/tests/*' -o -path '*/testdata/*' \
  -o -path '*/test-data/*' -o -path '*/src/test/*' \
  -o -path '*fixture*' -o -path '*/examples/*' -o -path '*/sample*' \
  -o -path '*/vendor/*' -o -path '*/third_party/*' -o -path '*/third-party/*' \
  -o -path '*/deps/*' -o -path '*/.deps/*' -o -path '*/lib/*' -o -path '*/libs/*' \
  ')' -prune -o )

# Emit genuine COMPILED-OUTPUT files under $1, AFTER pruning. A file counts ONLY when
# file(1) magic CONFIRMS it is genuinely compiled -- a build extension in the NAME is not
# enough (a text file named notes.class or legacy.dll must NOT count; that false-built=1 is
# how a text-only tree slips through to a false CLEAN). Every branch reads the magic and
# matches ONLY the file(1) type field after the colon (`:[^:]*...`) -- never the path, so an
# "elf"/"class"/"dll" in a filename or dir name is ignored. -exec file {} + survives spaces
# in filenames. A committed *-wrapper.jar and any pruned test/vendor .so are NOT counted.
compiled_out() {
  # native object/library/archive: ELF, Mach-O, or ar archive.
  find "$1" "${prune_expr[@]}" -type f \( -name '*.so' -o -name '*.o' \
        -o -name '*.a' -o -name '*.dylib' \) -exec file {} + 2>/dev/null \
    | grep -E ':[^:]*(\bELF\b|Mach-O|ar archive)' | sed 's/:.*//'
  # Windows PE artifacts: PE32 / MS-DOS / executable.
  find "$1" "${prune_expr[@]}" -type f \( -name '*.dll' -o -name '*.exe' \
        -o -name '*.pyd' \) -exec file {} + 2>/dev/null \
    | grep -E ':[^:]*(PE32|MS-DOS|executable)' | sed 's/:.*//'
  # Java bytecode: 'compiled Java class'.
  find "$1" "${prune_expr[@]}" -type f -name '*.class' -exec file {} + 2>/dev/null \
    | grep -E ':[^:]*compiled Java class' | sed 's/:.*//'
  # Java archive (exclude maven/gradle wrapper jars): 'Java archive' or 'Zip archive'.
  find "$1" "${prune_expr[@]}" -type f -name '*.jar' ! -name '*-wrapper.jar' \
        -exec file {} + 2>/dev/null \
    | grep -E ':[^:]*(Java archive|Zip archive)' | sed 's/:.*//'
  # Extensionless ELF binaries, post-prune (a built Go ./app).
  find "$1" "${prune_expr[@]}" -type f ! -name '*.*' -exec file {} + 2>/dev/null \
    | grep -E ':[^:]*\bELF\b' | sed 's/:.*//'
}

# BUILT=1 only on genuine compiled output. This whole-tree scan also governs
# target/ build/ dist/ out/: a config-only build/ produces NO compiled output post-prune
# and therefore does NOT set built=1 -- "non-empty" alone is never sufficient.
if [ -n "$(compiled_out "$TREE" | head -n1)" ]; then BUILT=1; fi

if [ "$FINDINGS" -eq 0 ] && [ "$BUILT" -eq 0 ]; then
  echo "VERDICT: INVALID (insufficient input -- build first). Layers 2-3 STILL MANDATORY."
  exit 2   # do NOT emit CLEAN
fi
echo "VERDICT: scan admissible -- layers 2-3 STILL MANDATORY (findings=$FINDINGS, built=$BUILT)."
```

An `exit 2` blocks the CLEAN path. **`built=1` means only "genuine compiled artifacts are present to scan," NOT "this tree was freshly built for arm64."** The gate confirms via `file(1)` magic that *some* real compiled output exists in the (post-prune) tree — nothing more. A committed compiled artifact left at the repo root (a hand-placed third-party `.so` or `.jar` that escaped the vendor/lib prune) can still satisfy `built=1`, so `built=1` is a **floor that admits the scan, not a guarantee the workload was built**. Before trusting a CLEAN, the agent MUST still (a) confirm the workload was actually compiled — ideally **for arm64** — and (b) run **layer 3** on every binary to check the ELF machine type (a fully x86 `target/` passes this gate but is not arm64-ready). Build the workload (produce `target/`, `dist/`, the fat-JAR, the `.so`s) and re-run all three layers against the *built* tree. A monorepo with 200 source files and one `target/app.jar` present passes the gate on the artifact, not a file tally — no false stop.

## Interpret findings: blocker vs. warning vs. clean

Only after the gate admits the scan, sort each finding (from any layer) into one bucket:

- **Blocker** — will not build or run on arm64 as-is: an x86-only native dependency with no arm64 build, hand-written x86 assembly on a hot path, a `<classifier>`-pinned amd64 JAR, an x86-only ELF that is actually executed, or a base image with no arm64 variant.
- **Warning** — probably fine, not proven: a dependency that *publishes* arm64 artifacts you have not built against, or an arch-guarded compile path. A warning is a task (build + test on arm64), not a pass.
- **Clean** — pure interpreted/managed code, dependencies with confirmed multi-arch artifacts, multi-arch base image — **and the gate passed.** Never collapse warnings into clean.

## Check every container base image for an arm64 variant

Independently of the code scan, verify the container layer. For every image referenced (each `FROM`, plus runtime sidecars, init containers, migration jobs) use the MCP's `check_image` / `skopeo` inspection to confirm the **exact reference in use** resolves to a manifest list containing a `linux/arm64` entry. A 100%-clean Go repo pinned to an amd64-only base tag is still blocked — by the image, not the code.

Two working-form gotchas so a literal follower does not hit the tool bugs:

- **`check_image` — use a tag, not a bare digest.** `check_image <repo>:<tag>` (e.g. `check_image nginx:1.27`) works. A fully-pinned `<repo>@sha256:<digest>` reference may **404** in `check_image`. When you only have a digest, resolve it to its manifest-list architectures with `docker manifest inspect <repo>@sha256:<digest>` (or `skopeo`, below), or check the corresponding tag.
- **`skopeo` — do NOT pre-prefix `docker://`.** The `skopeo` tool adds the `docker://` transport itself; pass the plain reference in `image` (e.g. `image=nginx:1.27`, optionally `transport=docker`, `raw=true` for the full manifest). A pre-prefixed `docker://nginx:1.27` becomes a double `docker://docker://…` and fails.

## Choose a remediation pattern per finding

- **Bump the base image to a multi-arch tag** — the most common fix; verify with `check_image`.
- **Find or pull an arm64 wheel / prebuild / classifier** — for Python/Node native modules and Maven native JARs, pin a version that publishes arm64 artifacts (or the correct arm64 `<classifier>`).
- **Rebuild the native dependency for arm64** — add a cross-compile or native-arm64 build; turns a checked-in x86 binary into a per-arch artifact.
- **Replace or guard x86 assembly / intrinsics** — provide a NEON path or a portable fallback behind an arch guard; highest effort, route to engineering.
- **Query the knowledge base** — `knowledge_base_search` often points at a known arm64 build flag or replacement package.

## Re-scan and emit a verdict

After remediation, re-run all three layers and the image check on the **built** workload, then close with a one-line verdict plus evidence:

- **CLEAN** — gate passed on a built tree; no blockers, no unverified warnings; multi-arch base confirmed.
- **PORTABLE WITH CHANGES** — findings exist but each has an assigned remediation pattern and owner.
- **BLOCKED** — at least one finding has no viable arm64 path yet.

Hand the verdict table to the cutover runbook. Only workloads with a re-scanned-CLEAN verdict **on the built tree** proceed to the [Karpenter arm64 cutover](./karpenter-migration.md) (a first-pass CLEAN on an un-built or under-scanned tree does NOT qualify); the multi-arch image each needs is produced by the [multi-arch CI pipeline](./multi-arch-pipelines.md).
