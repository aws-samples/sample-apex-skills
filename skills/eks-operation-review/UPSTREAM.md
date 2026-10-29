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

1. **`steering/` -> `references/` rename.** Upstream's progressive-disclosure docs live under `steering/`. Apex renames them to `references/`, the Anthropic skill spec's canonical name for additional documentation (this also avoided a clash with apex's former top-level `steering/` directory, removed in v2). The sync script renames the directory on copy and rewrites all internal cross-refs from `steering/` to `references/` inside `SKILL.md` and the 11 progressive-disclosure files.

2. **`SKILL.md` description block-scalar flattening.** Upstream uses YAML folded-scalar form (`description: >` followed by indented lines). Apex's catalog generator reads the same line as the key, so the catalog row would render just `>`. The sync flattens the block scalar to a single `description: <one line>` entry. Wording is preserved byte-for-byte; only the YAML representation changes.

3. **`SKILL.md` body path fix.** Upstream's body says "Read and follow `.claude/commands/eks-operation-review.md`": that path doesn't exist in apex. The slash-command content is apex's own workflow, kept outside this folder at `skills/apex/runbooks/eks-operation-review/eks-operation-review.md`. The sync rewrites the reference to that file, relative to this skill's folder (`../apex/runbooks/eks-operation-review/eks-operation-review.md`).

4. **`SKILL.md` Prerequisites MCP line.** Upstream lists "MCP servers configured in `.mcp.json`" as a prerequisite. Apex doesn't ship `.mcp.json`; MCP setup is handled by the `eks-mcp-server` skill. The sync rewrites the line to point users at that skill instead.

The upstream description **wording** is NOT rewritten — skill-creator's restrained-style content is already apex-compatible. Only the YAML representation is flattened (Edit #2).

Everything else is byte-for-byte from upstream.

## To propose changes

Open a PR against the upstream repo:
https://github.com/aws-samples/sample-eks-operation-review-skill.git

Then re-run the sync script here.
