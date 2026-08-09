# Agent Scope Boundaries

> **Part of:** [graviton-migration](../SKILL.md)

Load this when a scope question comes up ("should the scanner touch this repo?", "is X part of this skill?"). It draws the line around what graviton-migration does and does not own, and carries the hard security guardrail on the scanner container.

## In scope

- Setting up the third-party **Arm migration MCP server** (`armlimited/arm-mcp:latest`) as a local stdio MCP server, across harnesses (Claude Code, Kiro, and any other via the self-correcting web-search path).
- Running the **three co-equal scan layers** to reach a per-workload arm64-readiness verdict:
  - Layer 1 — the Arm MCP source scanner (`migrate_ease_scan`) and image-arch tools (`check_image`, `skopeo`).
  - Layer 2 — dependency-manifest / lockfile parsing for arch-specific packages.
  - Layer 3 — binary/JAR ELF scanning for arm64 build presence.
- Reconciling the three layers into one verdict and interpreting blockers vs. warnings vs. clean.
- **Node capacity planning and cutover** — a taint-first arm64 Karpenter NodePool, canary with tolerations + nodeSelector, progressive replica shift, cross-arch spread, and cleanup.
- **Validation on arm64** under realistic load against the x86 baseline.
- **Multi-arch CI** — updating the build pipeline to publish an amd64+arm64 manifest list so the change sticks.
- Producing a **lightweight conversational findings summary / runbook** on request (not a mandated file contract).

## Out of scope — route elsewhere

- **"How much would Graviton save me?" / Spot+Graviton adoption scoring / dollar-denominated findings** → `eks-cost-intelligence`. The MCP's sizing/perf tools are planning context only, never the cost deliverable.
- **"Should I even adopt Graviton?" advisory architecture judgment** with no migration to run → `eks-best-practices`.
- **Setting up a non-Graviton MCP server** (e.g. the EKS MCP server for cluster ops) → `eks-mcp-server`. This skill only sets up the Arm migration MCP.
- **General EKS upgrade readiness, recon, or operational review** → the respective eks-* skills. Graviton-migration does not score cluster health.
- **Emitting a mandated `graviton-validation/` folder or batch file artifacts** — out of scope by design; this is a conversational skill.
- **Modifying application source to fix arm64 blockers automatically** — the skill diagnoses and guides; it does not silently rewrite a user's code. Confirm before any edits.

## Security guardrail — the scanner container is NOT a trust boundary

**Do NOT mount repos containing secrets or credentials into the scanner container.** The `-v "$(pwd)":/workspace:ro` mount is read-only for the *filesystem* only — it is **not** a trust boundary:

- The third-party `armlimited/arm-mcp` image (Arm Ltd) **reads all of your source** inside `/workspace`.
- It **makes outbound network calls** (the image-arch tools `check_image`/`skopeo` reach registries, and the host-execution tools `apx_recipe_run`/`sysreport` can SSH out to a target host) — so it is not offline, and anything it reads could in principle leave the host. The `knowledge_base_search` tool is *not* one of those network calls: it searches a **local** knowledge-base index bundled in the image (a usearch `.bin` vector index baked into the container), so it does not itself reach the network.
- `:ro` stops the container writing to or deleting your source; it does nothing to stop the container reading secrets, env-file contents, `.git` history, or private keys that happen to sit in the tree, and forwarding them over the network.

Before mounting:

1. Scan the working tree for secrets (`.env`, `*.pem`, `id_rsa`, cloud credential files, `.git-credentials`) and either remove them from the tree or mount a clean, source-only checkout that excludes them.
2. Prefer mounting a **clean checkout** of just the source to migrate, not a developer working directory full of local config.
3. Treat this exactly like running any untrusted third-party binary against a private repo — because that is what it is. Pin a specific published image tag rather than `:latest` for reproducibility, and confirm the image before the first pull.
4. Keep the server **credential-free** — it scans source and manifests, it does not need AWS credentials; never inject them into the MCP entry.
5. If a tool genuinely needs to write output, give it a *dedicated* writable mount at its own path (e.g. `-v /tmp/arm-mcp-out:/out`) rather than dropping `:ro` on the source tree.

**Not every tool's effect stays inside the container.** `apx_recipe_run` **executes on the host**, outside the container's `:ro` isolation, and can target a **remote** host (localhost or a named remote), not just the machine you are on. `sysreport_instructions` does not itself execute anything — it *returns host commands* — but the risk is identical the moment you **run those returned commands** (via Bash) on the host. The mount-safety discipline above does nothing for either: the host-execution step is effectively arbitrary host command execution. Treat every such invocation accordingly — show the exact command **and its target host** and get explicit user confirmation before executing it, and never run against an un-named or implicit host.
