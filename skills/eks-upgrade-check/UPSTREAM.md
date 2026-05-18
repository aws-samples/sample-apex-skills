# Upstream Provenance

This skill is **vendored** from an upstream repo. Do not edit files here directly — your changes will be overwritten by the next sync.

| Field | Value |
|---|---|
| Source repo | https://github.com/aws-samples/sample-eks-upgrade-skill.git |
| Source path | `.claude/skills/eks-upgrade/` |
| Refresh command | `./misc/sync-eks-upgrade-skill.sh` |
| License | See `LICENSE` (copied verbatim from upstream) |

## Local modifications applied at sync time

The sync script applies one deterministic edit to the upstream `SKILL.md`:

- The `### MCP Server Setup` section is replaced. Apex does not ship a project-root `.mcp.json`; MCP setup is delegated to the `eks-mcp-server` skill in this repo.

Everything else is byte-for-byte from upstream.

## To propose changes

Open a PR against the upstream repo:
https://github.com/aws-samples/sample-eks-upgrade-skill.git

Then re-run the sync script here.
