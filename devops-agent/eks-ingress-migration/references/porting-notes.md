# Porting Notes — eks-ingress-migration

This file documents the differences between the Claude Code version and the DevOps Agent port. It is for maintainers, not for the agent to read during execution.

## What Was Dropped

| Item | Reason |
|------|--------|
| `tools/report_to_html.py` | No script execution in Agent Space; markdown-only output |
| HTML report generation | No browser/rendering runtime available |
| Manifest export (`current/` and `target/` YAML) | Agent role is assessment only — no file generation beyond the report |
| `topology.json` output | No HTML/3D consumer in Agent Space |
| `tools/` directory | No script execution permitted |

## What Was Modified

| File | Change |
|------|--------|
| `SKILL.md` | Rewritten execution model: fully autonomous (no interactive prompts, no hard-stops), multi-cluster assessment, error contract added, skip-list for porting-notes.md |
| `references/report-generation.md` | Rewritten for markdown-only output; removed HTML generation, manifest export, and topology.json references |
| `references/traffic-routing.md` | Added DevOps Agent port note marking deep-inspection commands (pods/exec, pod creation) as inapplicable under read-only RBAC |
| `references/migration-plan.md` | Added assessment-only framing note clarifying that mutating commands are documented steps, never executed |

## What Was Preserved

All other reference files are byte-identical copies from the upstream Claude Code skill:

- `references/ingress-discovery.md`
- `references/ingress-resources.md`
- `references/dns-certificates.md`
- `references/migration-risk.md`
- `references/gateway-api.md`
- `references/alb-migration.md`
- `references/atx-guide.md`
- `references/iam-policy.json`

## Runtime Differences

| Aspect | Claude Code | DevOps Agent |
|--------|-------------|--------------|
| Tool access | `aws` CLI, `kubectl`, EKS MCP server | AWS APIs and Kubernetes APIs via Agent Space |
| MCP | Local `.mcp.json` with `eks-mcp-server` | No MCP — direct API calls only |
| Script execution | Python scripts in `tools/` | None — no scripts directory, no runtime |
| Interactive prompts | Shows discovery table, asks user to choose cluster | Fully autonomous — assesses all discovered clusters |
| RBAC posture | Full cluster access (user's kubeconfig) | Read-only Agent Space role (get/list only) |
| Cluster selection | Single cluster, user-confirmed | All clusters assessed; separate report section per cluster |
| Report format | Markdown + HTML + topology JSON + manifest YAML | Markdown only |
