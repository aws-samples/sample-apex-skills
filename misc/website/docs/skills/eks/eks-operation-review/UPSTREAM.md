---
title: "Upstream Provenance"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-operation-review/UPSTREAM.md
format: md
---

:::info[Source]
This page is generated from [skills/eks-operation-review/UPSTREAM.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-operation-review/UPSTREAM.md). Edit the source, not this page.
:::


:::info[Vendored skill]
This skill is sourced from [eks-operation-review](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-operation-review), also maintained by the APEX team.
:::

# Upstream Provenance

This skill is **vendored** from an upstream repo. Do not edit files here directly — your changes will be overwritten by the next sync.

| Field | Value |
|---|---|
| Source repo | https://github.com/aws-samples/sample-eks-operation-review-skill.git |
| Source path | repo root (`SKILL.md`, `steering/`, `tools/`, `LICENSE`) |
| Refresh command | `./misc/sync-eks-operation-review-skill.sh` |
| License | See `LICENSE` (copied verbatim from upstream — MIT-0) |

## Local modifications applied at sync time

The sync script applies four deterministic edits to upstream content:

1. **`steering/` -> `references/` rename.** Upstream's progressive-disclosure docs live under `steering/`, but apex already uses a top-level `steering/` directory at the repo root for workflow orchestration (different concept). The sync script renames the directory on copy and rewrites all internal cross-refs from `steering/` to `references/` inside `SKILL.md` and the 11 progressive-disclosure files. This aligns the layout with the Anthropic skill spec's canonical name for "additional documentation agents read on demand."

2. **`SKILL.md` description block-scalar flattening.** Upstream uses YAML folded-scalar form (`description: >` followed by indented lines). Apex's catalog generator reads the same line as the key, so the catalog row would render just `>`. The sync flattens the block scalar to a single `description: <one line>` entry. Wording is preserved byte-for-byte; only the YAML representation changes.

3. **`SKILL.md` body path fix.** Upstream's body says "Read and follow `.claude/commands/eks-operation-review.md`" — that path doesn't exist in apex (the slash-command content is baked into apex's `steering/workflows/eks-operation-review.md` instead). The sync rewrites the reference to point at the apex workflow via the `~/.claude/apex-steering` symlink convention used by other apex slash commands.

4. **`SKILL.md` Prerequisites MCP line.** Upstream lists "MCP servers configured in `.mcp.json`" as a prerequisite. Apex doesn't ship `.mcp.json`; MCP setup is handled by the `eks-mcp-server` skill. The sync rewrites the line to point users at that skill instead.

The upstream description **wording** is NOT rewritten — skill-creator's restrained-style content is already apex-compatible. Only the YAML representation is flattened (Edit #2).

Everything else is byte-for-byte from upstream.

## To propose changes

Open a PR against the upstream repo:
https://github.com/aws-samples/sample-eks-operation-review-skill.git

Then re-run the sync script here.
