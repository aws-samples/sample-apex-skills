---
title: "Porting Notes — eks-ingress-migration"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/devops-agent/eks-ingress-migration/references/porting-notes.md
format: md
---

:::info[Source]
This page is generated from [devops-agent/eks-ingress-migration/references/porting-notes.md](https://github.com/aws-samples/sample-apex-skills/blob/main/devops-agent/eks-ingress-migration/references/porting-notes.md). Edit the source, not this page.
:::

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
| `SKILL.md` reference table | Upstream's conditional skip-list removed — the autonomous agent reads all reference files to assess all migration paths in a single pass |
| `references/report-generation.md` | Rewritten for markdown-only output; removed HTML generation, manifest export, and topology.json references |
| `references/traffic-routing.md` | Added DevOps Agent port note marking deep-inspection commands (pods/exec, pod creation) as inapplicable under read-only RBAC |
| `references/migration-plan.md` | Added assessment-only framing note clarifying that mutating commands are documented steps, never executed |

## What Was Port-Authored

| File | Notes |
|------|-------|
| `references/iam-policy.json` | Created for the port — defines AmazonAIOpsAssistantPolicy scoped permissions; no upstream equivalent exists |
| `references/porting-notes.md` | This file |

## What Was Preserved

26 files are byte-identical copies from the upstream Claude Code skill:

**Reference docs (10):**
- `references/ingress-discovery.md`
- `references/ingress-resources.md`
- `references/dns-certificates.md`
- `references/migration-risk.md`
- `references/gateway-api.md`
- `references/alb-migration.md`
- `references/atx-guide.md`
- `references/atx/td_ingress-nginx-lbc/transformation_definition.md`
- `references/atx/td_ingress-nginx-lbc/summaries.md`
- `references/atx/td_ingress-nginx-lbc/document_references/navigating-nginx-ingress-retirement.md`

**Sample YAML (16):**
- `references/samples/alb/01–08-*.yaml` (8 files)
- `references/samples/nginx/01–08-*.yaml` (8 files)

> **Known upstream issue:** `ingress-resources.md:91` contains a stale "for the 3D visualization" reference inherited from upstream; intentionally preserved as a byte-copy (filed as upstream issue).

## Runtime Differences

| Aspect | Claude Code | DevOps Agent |
|--------|-------------|--------------|
| Tool access | `aws` CLI, `kubectl`, EKS MCP server | AWS APIs and Kubernetes APIs via Agent Space |
| MCP | No `.mcp.json` required; upstream uses Claude Code tool calls (Bash, Read) for cluster access | No MCP — the port uses AWS DevOps Agent's native Kubernetes API integration via AmazonAIOpsAssistantPolicy |
| Script execution | Python scripts in `tools/` | None — no scripts directory, no runtime |
| Interactive prompts | Shows discovery table, asks user to choose cluster | Fully autonomous — assesses all discovered clusters |
| RBAC posture | Full cluster access (user's kubeconfig) | Read-only Agent Space role (get/list only) |
| Cluster selection | Single cluster, user-confirmed | All clusters assessed; separate report section per cluster |
| Report format | Markdown + HTML + topology JSON + manifest YAML | Markdown only |
