---
title: "Porting Notes — eks-recon"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/devops-agent/eks-recon/references/porting-notes.md
format: md
---

:::info[Source]
This page is generated from [devops-agent/eks-recon/references/porting-notes.md](https://github.com/aws-samples/sample-apex-skills/blob/main/devops-agent/eks-recon/references/porting-notes.md). Edit the source, not this page.
:::

# Porting Notes — eks-recon

This file documents the differences between the Claude Code version and the DevOps Agent port. It is for maintainers, not for the agent to read during execution. **This file is excluded from the uploaded skill zip** (see the `-x './references/porting-notes.md'` flag in the README's zip instructions) — it ships in the repository for maintainers only.

> **Staleness check:** the table below describes the upstream skill at a point in time and can drift as `skills/eks-recon/` evolves. Re-verify each row against upstream when materially changing either copy, and update the date here. Last verified: 2026-07-19.

## Differences from Claude Code Version

| Aspect | Claude Code (`skills/eks-recon/`) | DevOps Agent (this skill) |
|--------|-----------------------------------|---------------------------|
| Execution model | Interactive — asks user to specify a cluster, prompts before CLI commands | Fully autonomous — Step 0 hard-stop decision table, no interactive prompts |
| Tool access | `aws` CLI, `kubectl`, `helm`, optional EKS MCP server | AWS control-plane APIs (read-only) + Kubernetes API via the Agent Space EKS access entry (read-only). No Bash, no kubectl, no MCP. |
| Kubernetes API access | `kubectl` against local kubeconfig, or MCP `list_k8s_resources` | EKS Access Entry binding the Agent Space role to `AmazonAIOpsAssistantPolicy` (cluster scope); expressed in references as "**Via Kubernetes API**" capability blocks, not `kubectl` pipelines |
| Subagent orchestration | 10 module subagents spawned in parallel via the Agent tool (`agents/*.md`) | No Agent tool — collapsed into SKILL.md reference-loading. Each module is a `references/<module>.md` file loaded on demand via the routing table. |
| Report generation | Markdown fact report + YAML artifact, written to `.eks-recon-report.{md,yaml}` | Same dual output (markdown primary + YAML machine artifact), generated directly — no file-writing scripts |
| Script dependencies | None (shell/kubectl pipelines inline) | None — no scripts permitted; detection is described declaratively |
| Cluster selection | Auto-discovers, asks user on ambiguity | Auto-selects single cluster; assesses all discovered on ambiguity; HARD STOP on API failure / zero clusters |
| MCP dependencies | References eks-mcp-server for richer live data | No MCP dependencies; uses Agent Space APIs directly |
| iac `evidence.type` enum | 4 values (`iac.md:337`): includes `workspace_files` and `cfn_stacks` | 2 values (`iac.md:186`): `cluster_tags` \| `in_cluster_crds`. Drops `workspace_files` (no filesystem in Agent Space) and `cfn_stacks` (the port's `iam-policy.json` grants no `cloudformation:*` permission). **No CFN fact is lost** — CloudFormation is still detected via `aws:cloudformation:*` cluster TAGS → `cluster_tags` evidence + `tags.cfn_stack_id`; only the `evidence.type` label changes. |

## Access-entry mechanism (why iam-policy.json has no `eks:AccessKubernetesApi`)

The DevOps Agent reaches the Kubernetes API through an **EKS Access Entry** that binds the Agent Space role to the AWS-managed `AmazonAIOpsAssistantPolicy` cluster-access policy (cluster scope), provisioned by `devops-agent/setup.sh`. The cluster's `authenticationMode` must include `API` (i.e. `API` or `API_AND_CONFIG_MAP`). Because the access entry — not an IAM action — grants K8s-API **authentication**, `iam-policy.json` contains **only AWS control-plane reads** and deliberately omits `eks:AccessKubernetesApi`.

**Authorization is narrower than authentication, and the two must not be conflated.** The access entry only authenticates the role; `AmazonAIOpsAssistantPolicy` supplies the RBAC, and it authorizes read-only `get`/`list` on **built-in API groups only** — core, `apps`, `batch`, `events.k8s.io`, `networking.k8s.io`, `storage.k8s.io`, and `metrics.k8s.io`. It grants **no CRD groups** (not even `apiextensions.k8s.io`). Consequently CRD-based facts (Karpenter `NodePool`/`EC2NodeClass`, Auto Mode `NodeClass`, Velero, `TargetGroupBinding`, VPA, policy engines, service mesh, GitOps, Crossplane/ACK) are **not** readable through the access entry alone — those reads return `403 Forbidden`. Capturing them requires binding the role to a **supplementary read-only ClusterRole** (or a broader access policy) granting `get`/`list` on the relevant CRD groups. Absent that, CRD-dependent sub-facts degrade to `unconfirmed` in the report's Coverage section — never `false`/`count: 0`. (See SKILL.md for the authoritative RBAC breakdown.)
