---
title: "graviton-migration"
description: "Execute a workload migration from x86 (amd64) to AWS Graviton (arm64) — set up the Arm migration MCP server for code, dependency, and container arm64-readiness scanning, then run the migration — pre-migration scanning, Karpenter arm64 node cutover, and multi-arch CI pipelines. Use when someone says \"migrate to Graviton\", \"move my workloads to arm64\", \"is my app arm64-ready\", \"graviton migration\", \"port this service to Graviton\", \"scan my code for arm64 blockers\", \"set up multi-arch container builds\", or \"cut my nodes over to arm64\". This skill owns migration EXECUTION (readiness scanning, NodePool cutover, multi-arch builds). Do NOT use for scoring Graviton cost savings, quantifying Spot/Graviton adoption, or \"how much would Graviton save me?\" (use eks-cost-intelligence); for advisory \"should I use Graviton?\" architecture guidance (use eks-best-practices); or for general, non-Graviton MCP server setup like the EKS MCP server (use eks-mcp-server)."
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/graviton-migration/SKILL.md
format: md
---

:::info[Source]
This page is generated from [skills/graviton-migration/SKILL.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/graviton-migration/SKILL.md). Edit the source, not this page.
:::


# Graviton Migration

This skill takes a workload from x86 (amd64) to AWS Graviton (arm64) end to end. It sets up a third-party **Arm migration MCP server** that exposes arm64-readiness scanning tools, then wraps a migration workflow around them: scan the code and containers, plan node capacity, cut over the nodes, validate, and make the CI pipeline build multi-arch images so the change sticks.

The value here is *execution*. Other skills in this catalog treat Graviton as a cost lever — they tell you how much you would save or whether you should adopt it. This skill does the actual move.

### Readiness scanning uses three co-equal input layers

The pre-migration scan is **not** a single MCP call. It draws on **three co-equal input layers**, and no one of them is "the spine":

1. **Layer 1 — Arm migration MCP** (this is layer 1 of 3, and the one with *known blind spots*). The MCP's source scanner and image-arch tools are fast and broad, but they miss things: transitively pulled native wheels/JARs, vendored prebuilt binaries, and dependencies resolved at build time rather than declared in source.
2. **Layer 2 — dependency-manifest parse (MANDATORY).** Independently parse the lockfiles/manifests (`requirements.txt`/`poetry.lock`, `go.mod`, `package-lock.json`, `pom.xml`/Gradle) to catch arch-specific packages the MCP scanner does not flag.
3. **Layer 3 — binary/JAR ELF scan (MANDATORY).** Inspect shipped binaries, `.so` files, and JARs with bundled native libs (ELF machine type) to confirm an arm64 build exists — the ground truth the other two layers only approximate.

Layers 2 and 3 are not optional add-ons. A "clean" MCP result alone is **not** a readiness verdict; reconcile all three layers before calling a workload portable. `references/scanner-workflow.md` and `references/dependency-knowledge.md` carry the per-layer detail.

## When NOT to Use This Skill

- **Scoring or quantifying Graviton savings** ("how much would Graviton save me?", "what's my Spot/Graviton adoption?") — use **eks-cost-intelligence**. That skill produces dollar-denominated findings and a cost score; this one changes the architecture.
- **Advisory "should I adopt Graviton?" architecture judgment** with no migration to run yet — use **eks-best-practices**.
- **Setting up a non-Graviton MCP server** (for example the EKS MCP server for cluster operations) — use **eks-mcp-server**. This skill only sets up the Arm migration MCP server.

If the user wants the *decision* or the *savings number*, route them. If they want the workload actually running on arm64, stay here.

---

## Part 1 — Set Up the Arm Migration MCP Server

The scanning tools this workflow depends on are delivered by a third-party MCP server from Arm Ltd (Apache-2.0), distributed as a Docker image. You run it locally as a stdio MCP server; it mounts the user's working directory so the scan tools can read their code.

### The invariant we own: the server entry

Regardless of which AI harness the user runs, the server is always the same container invoked the same way:

```
docker run --rm -i -v "$(pwd)":/workspace:ro armlimited/arm-mcp:latest
```

- `--rm` — remove the container when the harness closes the connection.
- `-i` — keep stdin open; MCP over stdio needs the pipe to stay live. Drive it from a harness (or an interactive/kept-open session) that holds stdin open for the whole exchange. A one-shot pipe (`echo '{...}' | docker run ... arm-mcp`) closes stdin as soon as the request is written, so the MCP process sees EOF and can exit before it returns results — the call comes back empty.
- Before mounting, make sure the working tree carries no secrets (`.env`, private keys, credential files) — or mount a clean, source-only checkout instead. The container reads *everything* under the mount and makes outbound network calls, so anything sensitive in `$(pwd)` is exposed (see the security guardrail in `references/agent-scope-boundaries.md`).
- `-v "$(pwd)":/workspace:ro` — mount the current directory (the repo to migrate) into the container, **read-only** (`:ro`) so the scanner cannot modify or delete your source. `:ro` guards the filesystem only — it is **not** the trust boundary: the container still reads all of your source and makes outbound network calls (the image-arch and host-execution tools reach registries / SSH out — see the tool list below), so treat this like running any third-party code against a private repo. Start with `:ro`. If a run shows the tool needs to write somewhere, give it a *dedicated* writable mount at its own path (e.g. `-v /tmp/arm-mcp-out:/out`) rather than dropping `:ro` and exposing the whole source tree.
- `armlimited/arm-mcp:latest` — the Arm migration MCP image. This is a third-party container (Arm Ltd) that runs against your source with network access, so treat it like any external dependency: for a reproducible setup, pin a specific published tag — or, stronger, a `@sha256:` digest — rather than the mutable `:latest`, and confirm the image before first pull.

**Everything else is just a per-harness wrapper around that one command.** The config *file location* and the *JSON/TOML shape* vary by harness; the `command`/`args` inside always resolve to the `docker run ... armlimited/arm-mcp` line above.

### Step 0: Prerequisite — Docker

The server is a container, so Docker (or a compatible runtime exposing the `docker` CLI) must be installed and running. Check first:

```
docker --version
```

If that fails, stop and have the user install Docker Desktop / Docker Engine and start the daemon before continuing. Nothing downstream works without it.

### Step 1: Confirm the harness

Ask which AI assistant the user is configuring. If they already said, confirm it back — do not re-ask. The two harnesses documented below are verified; anything else takes the self-correcting path in Step 3.

### Step 2: Write the config (Claude Code and Kiro)

Both harnesses use the same `mcpServers` object shape — an entry keyed by a server name, with a `command` and an `args` array. We set `command` to `docker` and put the run flags plus the image in `args`. The only real difference between the two is *which file* the block goes in.

| Harness | Config file | Scope |
|---------|-------------|-------|
| Claude Code | `.mcp.json` (repo root) | Project — travels with the repo, best for a migration |
| Claude Code | `~/.claude.json` (via `claude mcp add -s user`) | User — all projects |
| Kiro | `.kiro/settings/mcp.json` | Project (workspace) |
| Kiro | `~/.kiro/settings/mcp.json` | User (global) |

The blocks below show `:latest` for readability. For a real migration, replace it with a specific published tag (see the pinning note under the invariant above) — `:latest` is fine to get started but not for a reproducible team setup.

**Claude Code** — `.mcp.json` (project scope). Claude Code expands `${VAR}` / `${VAR:-default}` in `command` and `args`, and it does **not** understand `${workspaceFolder}` (that is a VS Code / Kiro variable). Use `${CLAUDE_PROJECT_DIR}` for the project root — but note it must carry a default (`${CLAUDE_PROJECT_DIR:-.}`) in a user-authored `.mcp.json` or `~/.claude.json`, because Claude Code injects `CLAUDE_PROJECT_DIR` into the *spawned server's* environment, not into its own config-parse environment. Without the default it will not expand:

```json
{
  "mcpServers": {
    "arm-mcp": {
      "command": "docker",
      "args": [
        "run", "--rm", "-i",
        "-v", "${CLAUDE_PROJECT_DIR:-.}:/workspace:ro",
        "armlimited/arm-mcp:latest"
      ]
    }
  }
}
```

Run Claude Code from the repo root so the `.` default resolves there if `CLAUDE_PROJECT_DIR` is unset.

**Kiro** — `.kiro/settings/mcp.json` (workspace scope). Kiro expands `${workspaceFolder}` to the open workspace root:

```json
{
  "mcpServers": {
    "arm-mcp": {
      "command": "docker",
      "args": [
        "run", "--rm", "-i",
        "-v", "${workspaceFolder}:/workspace:ro",
        "armlimited/arm-mcp:latest"
      ]
    }
  }
}
```

Notes:

- Each harness uses its own project-root variable — `${CLAUDE_PROJECT_DIR}` for Claude Code, `${workspaceFolder}` for Kiro. If a harness expands neither, substitute the **absolute path** to the repo root (for example `-v /home/me/project:/workspace:ro`). The container reads `/workspace`, so whatever you mount there is what gets scanned.
- The server needs no AWS credentials — it scans source and container manifests rather than calling AWS APIs, so keep the entry credential-free. (It does make outbound calls for the image-manifest/registry checks — and host-execution tools can SSH out — so it is not fully offline; the knowledge-base lookup, by contrast, is a local bundled index. Either way, not AWS-authenticated.)
- Pick project scope for a real migration so the config lives with the repo the team is porting.

### Step 3: Self-correcting guard for any other harness

If the user's harness is **not** Claude Code or Kiro (for example Cursor, Windsurf, VS Code/Cline, or something newer), **do not guess its MCP config format from memory.** MCP config schemas — the file path and the exact server-entry shape — are precisely the harness-specific detail that gets recited wrong and drifts as tools change releases. A confidently-wrong config file is worse than no config, because it looks correct and fails silently.

Instead:

1. **Web-search the current MCP-server setup convention for that specific harness.** Look for two facts: (a) the config file location, and (b) the server-entry schema (is it an `mcpServers` object like above? a different key? TOML instead of JSON? a UI-only "add server" flow?).
2. **Adapt the invariant to it.** Keep the server entry exactly — `command: docker`, args = the run flags + `armlimited/arm-mcp:latest`. Only reshape the *wrapper* around it to match what the search turned up.
3. Show the user the file path and the adapted block, and explain which parts came from the search.

The `docker run ... armlimited/arm-mcp:latest` server entry is the stable invariant; only the config wrapper varies. This is what keeps the skill portable without hardcoding every harness.

### Step 4: Verify it works

1. **Restart** the harness (or reload its MCP config) so it picks up the new server.
2. **Confirm the tools appeared** — ask the harness to list available MCP tools and check for the Arm scan tools (the source scanner, image-arch inspectors, the knowledge-base search, and the performance/report tools — see the tool list below). Run the server's `tools/list` to see the current tool set; the exact count is set by the server version, not fixed here.
3. **Smoke test** — run the source scanner against the mounted repo and confirm it returns findings rather than an error. Confirm the tool's real registered name and its supported languages from `tools/list` first (do not assume `migrate_ease_scan`, and do not assume the language set — the server version can change it). It takes a required `scanner` (a supported language) plus `arch`/`git_repo`/`output_format`/`extra_args` — note there is **no `path` argument**; the scan target is the `/workspace` mount, and `arch` defaults to `armv8-a` (`aarch64` is rejected). A valid smoke call is `{"scanner":"go","arch":"armv8-a"}`.

### Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `docker: command not found` / daemon errors | Docker not installed or not running | Install Docker and start the daemon; re-run `docker --version` |
| First call hangs, then tools appear | Image being pulled on first run | Pre-pull with `docker pull armlimited/arm-mcp:latest`; retry |
| Image pull fails | No network / registry auth / typo | Confirm connectivity and the exact image name `armlimited/arm-mcp` (and the tag you pinned) |
| Tools never appear after restart | Wrong config file or invalid JSON | Verify the path matches the harness table; validate JSON (`python3 -c "import json;json.load(open('.mcp.json'))"`) |
| Scanner sees no files | Wrong mount | Confirm `-v` points at the repo root and resolves to an absolute path inside the harness |

### The tools this MCP exposes

The image surfaces the tools below. The exact set and count are set by the server version, not fixed here — run `tools/list` to see the current tools. Frame them as capabilities the workflow references call into (feeding layer 1 of the three-layer scan), not as anything this skill implements:

- **`migrate_ease_scan`** — the MigrateEase-style source-readiness scan; runs a per-language scanner over the mounted workspace or a remote Git repo and reports arm64-readiness blockers. This is the primary layer-1 tool. (Confirm the name and supported languages from `tools/list` — the names here are not frozen fact.) Params: `scanner` (required, a supported language), `arch` (default `armv8-a`; `aarch64` rejected), `git_repo`, `output_format`, `extra_args` — **no `path` arg**; it scans the `/workspace` mount.
- **`check_image`** — reports the architectures a Docker image reference supports.
- **`skopeo`** — inspects a container image/manifest list *remotely* (no pull) to confirm an arm64 variant exists; overlaps `check_image` for the layer-1 image check.
- **`knowledge_base_search`** — searches an Arm/Graviton porting knowledge base for remediation guidance. This is a **local** index bundled in the image (a usearch vector index baked into the container), not a network call; preserve any returned source URLs verbatim.
- **`mca`** — assembly/object-code performance analyzer (predicts IPC / bottlenecks across CPU targets).
- **`apx_recipe_run`** — runs a sample workload via a Performix recipe (e.g. `code_hotspots`) on localhost or a remote host and interprets the results (host execution is outside container isolation — review the commands and target with the user first).
- **`sysreport_instructions`** — returns instructions for the `sysreport` host-hardware inspection tool (host execution is outside container isolation — review commands with the user first).

Do not treat these identifiers as frozen: the registered tool names and count can change between image releases. When you actually connect, list the MCP's tools and use the names it surfaces rather than assuming this set. (Note on versions: the server's `serverInfo.version` and the startup banner report a **FastMCP framework** version, not the app version — do not cite it as the Arm-MCP version. If you need to pin something, pin a specific published image tag rather than `:latest`.)

---

## Part 2 — Migration Workflow

Once the Arm MCP is verified, run the migration as a numbered flow. Each step names the reference file to load for the detail. Load a reference with the Read tool at `${CLAUDE_SKILL_DIR}/references/<file>.md` **only when you reach that step** — do not front-load them.

**Platform scope:** the readiness scan and multi-arch build steps (steps 1–2 and step 6) are platform-agnostic, but the **node-cutover runbook (steps 3–4, `karpenter-migration.md`) assumes EKS with Karpenter v1.** On managed node groups, EKS Auto Mode, ECS, Fargate, plain EC2/ASG, or Lambda, keep the readiness verdict but adapt the cutover to that platform's own capacity model.

1. **Assess readiness — run all three scan layers.** Identify candidate workloads, then for each one work the three co-equal input layers (do not stop at a clean MCP result):
   - *Layer 1* — run the source scanner (the MigrateEase-style tool, `migrate_ease_scan` at time of writing; confirm its registered name and supported languages from the tool list — do not assume them) with `scanner=<supported-lang>` and `arch=armv8-a` (the default; no `path` arg — it scans the `/workspace` mount), plus the image-arch tools over each repo.
   - *Layer 2 (mandatory)* — parse the dependency manifests/lockfiles for arch-specific packages the scanner misses.
   - *Layer 3 (mandatory)* — ELF-scan shipped binaries/`.so`/JARs to confirm an arm64 build exists.
   Reconcile all three into one verdict per workload (blockers vs. warnings vs. clean).
   → Load `${CLAUDE_SKILL_DIR}/references/scanner-workflow.md` for the full 3-layer scan procedure — including the Layer-3 binary/JAR ELF scan (file/readelf) and the fail-closed built-source gate — and `${CLAUDE_SKILL_DIR}/references/dependency-knowledge.md` for the Layer-2 dependency-manifest parse and native-dependency arm64 version floors.
2. **Scan container images.** For every base image and shipped image, use the image-arch tools (`check_image` / `skopeo`) to confirm an arm64 / multi-arch (manifest list) variant exists before assuming the workload is portable.
   → covered in `${CLAUDE_SKILL_DIR}/references/scanner-workflow.md`
3. **Plan node capacity.** Decide how arm64 capacity enters the cluster (a dedicated arm64 NodePool, taint-first) and how you will spread across architectures during the transition.
   → Load `${CLAUDE_SKILL_DIR}/references/karpenter-migration.md`
4. **Cut over.** Add the tainted arm64 NodePool, put matching tolerations + nodeSelector on a canary, deploy a multi-arch image, validate the pod runs on arm64, then move the workload to arm64 — by default a rolling update of the one existing Deployment onto arm64 (abort = `kubectl rollout undo`); use the advanced two-per-arch-Deployment pattern only if you need a tunable percentage soak. Run the arm64 NodePool on `on-demand` (not Spot) through the canary/soak.
   **Hard precondition:** cutover requires a reconciled CLEAN verdict **from a re-scan of the built tree** (a first-pass CLEAN on an un-built or under-scanned tree does NOT count) + a confirmed manifest-list (multi-arch) arm64 image per workload — do not enter the cutover runbook otherwise. A CLEAN 3-layer verdict means only "no *known* build/run blocker found" — it is a floor, not proof of correctness or performance, and can still miss guarded/off-list intrinsics and silent correctness bugs (e.g. the signed-`char` class). Canary correctness testing and perf validation (step 5) are still required.
   → covered in `${CLAUDE_SKILL_DIR}/references/karpenter-migration.md`
5. **Validate.** Confirm the workload is healthy on arm64 under realistic load, comparing against the x86 baseline. Retire the x86 capacity only *after* a soak period (it is your rollback target — see the runbook's retirement step), not immediately on validation.
   → Load `${CLAUDE_SKILL_DIR}/references/perf-validation.md`
6. **Lock it in with multi-arch CI.** Update the build pipeline to publish an amd64+arm64 manifest list on every build so future images stay portable.
   → Load `${CLAUDE_SKILL_DIR}/references/multi-arch-pipelines.md`

---

## Suggested findings summary / runbook shape

This is a conversational skill, not a batch service — it does **not** emit a mandated `graviton-validation/` folder or a file contract. As you work, just keep a running summary in the conversation and offer it back when the user wants something to paste into a ticket or runbook. A light shape that tends to be useful:

- **Per-workload readiness verdict** — one line each: `clean` / `portable-with-changes` / `blocked`, plus the single biggest blocker, and *which* of the three scan layers surfaced it.
- **Cutover plan** — the arm64 NodePool decision, the canary target, and the rollback trigger.
- **Validation deltas** — a couple of before/after numbers on arm64 vs x86 under load (latency, throughput, error rate).
- **CI change** — the one-line "now publishes a multi-arch manifest list" note.

Produce it inline as markdown if asked; do not create files unless the user explicitly wants them written out. Scope questions ("should the scanner touch this repo?", "is X in scope?") are answered by `references/agent-scope-boundaries.md`.

---

## Interaction Rules

1. **Do not guess the harness.** If it is not Claude Code or Kiro, take the Step 3 self-correcting path (web-search, then adapt the invariant). Never recite a config schema from memory for an undocumented harness.
2. **Read the reference file before generating its config or manifests.** Do not produce a NodePool, a scan interpretation, or a CI block from memory — load the reference at `${CLAUDE_SKILL_DIR}/references/<file>.md` first.
3. **Check Docker before writing MCP config.** `docker --version` is the gate; if it fails, stop there.
4. **Scan for secrets before mounting the project tree.** Before the MCP server container first starts against the mount (Step 4 — the mount attaches at container launch, before the smoke-test scan), scan `$(pwd)` for secrets (`.env`, private keys, credential files — and secrets committed in `.git` history, which the container also reads); if any exist, exclude them from the mounted checkout or mount a clean, source-only checkout first. The container reads everything under the mount and makes outbound network calls, so this gate runs before the container ever launches — a clean smoke test does not excuse skipping it.
5. **Do not retry a failed file read or command more than once.** Surface the exact error to the user and let them resolve it.
6. **Stay in your lane.** If the user pivots to "how much will this save?" or "should I even do this?", hand off to eks-cost-intelligence / eks-best-practices rather than answering here.
7. **Confirm before destructive cutover steps** (removing the x86 NodePool, rolling all replicas, **removing the arm64 NodePool taint, or deleting the original workload Deployment**). Validate the canary first.
8. **Gate host command execution.** `apx_recipe_run` runs OUTSIDE the container's isolation — on localhost or a remote host. `sysreport_instructions` only *returns* host commands, but the moment you **execute those returned commands** (via Bash) they run on the host just the same. Either way the host-execution step is arbitrary command execution outside the container: show the user the exact command and target and get explicit confirmation **before executing it** — do not run `apx_recipe_run`, and do not run the commands `sysreport_instructions` hands back, until then. Never run against a host the user has not named.
