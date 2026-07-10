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
| `SKILL.md` | Rewritten execution model: fully autonomous (no interactive prompts, no hard-stops), multi-cluster assessment, error contract added, skip-list for porting-notes.md; Report Structure table expanded (6th group added) |
| `SKILL.md` reference table | Upstream's conditional skip-list removed — the autonomous agent reads all reference files to assess all migration paths in a single pass |
| `references/report-generation.md` | Rewritten for markdown-only output; removed HTML generation, manifest export, and topology.json references; footer added (port-authored — no footer in upstream); Tier-B semantics deliberately diverge from upstream (upstream caps at Impact 3, port allows migration-path-reference override to Impact 5); Output Contract section added for multi-file output |
| `references/traffic-routing.md` | Added DevOps Agent port note marking deep-inspection commands (pods/exec, pod creation) as inapplicable under read-only RBAC; removed stale topology-JSON and 3D-visualization references (lines 90, 94, 103); topology-JSON references replaced with report-section references at lines 90, 94, 103 |
| `references/migration-plan.md` | Added assessment-only framing note clarifying that mutating commands are documented steps, never executed |

## What Was Port-Authored

| File | Notes |
|------|-------|
| `references/iam-policy.json` | Custom IAM identity policy defining the Agent Space role's minimum permissions for ingress assessment (read-only EKS/EC2/ELB/ACM actions). Separate from `AmazonAIOpsAssistantPolicy` which is an AWS-managed EKS cluster-access policy attached via access entries in setup.sh |
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
- 8 sample YAMLs per directory (01…08 prefixed)
  - `references/samples/alb/`
  - `references/samples/nginx/`

> **Known upstream issue:** `ingress-resources.md:91` contains a stale "for the 3D visualization" reference inherited from upstream; intentionally preserved as a byte-copy (filed as upstream issue).

## Runtime Differences

| Aspect | Claude Code | DevOps Agent |
|--------|-------------|--------------|
| Tool access | EKS MCP server (primary), `aws` CLI + `kubectl` (fallback) | AWS APIs and Kubernetes APIs via Agent Space |
| MCP | EKS MCP server for cluster operations; falls back to aws CLI + kubectl when MCP unavailable | No MCP — native Kubernetes API integration via AmazonAIOpsAssistantPolicy |
| Script execution | Python scripts in `tools/` | None — no scripts directory, no runtime |
| Interactive prompts | Shows discovery table, asks user to choose cluster | Fully autonomous — assesses all discovered clusters |
| RBAC posture | Full cluster access (user's kubeconfig) | Read-only Agent Space role (get/list only) |
| Cluster selection | Multi-region discovery, user selects cluster(s) | All clusters assessed; one report file per cluster + summary file |
| Report format | Markdown + HTML + topology JSON + manifest YAML | Markdown only |
