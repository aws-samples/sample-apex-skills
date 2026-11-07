# Porting Notes — eks-recon

This file documents the differences between the Claude Code version and the DevOps Agent port. It is for maintainers, not for the agent to read during execution. **This file is excluded from the uploaded skill zip** (see the `-x './references/porting-notes.md'` flag in the README's zip instructions) — it ships in the repository for maintainers only.

> **Staleness check:** the table below describes the upstream skill at a point in time and can drift as `skills/eks-recon/` evolves. Re-verify each row against upstream when materially changing either copy, and update the date here. Last verified against source: 2026-10-31. This is a source comparison, not a native Agent Space execution test.

## Differences from Claude Code Version

| Aspect | Claude Code (`skills/eks-recon/`) | DevOps Agent (this skill) |
|--------|-----------------------------------|---------------------------|
| Execution model | Interactive — asks user to specify a cluster, prompts before CLI commands | Fully autonomous — Step 0 hard-stop decision table, no interactive prompts |
| Tool access | `aws` CLI, `kubectl`, `helm`, optional EKS MCP server | AWS control-plane APIs (read-only) + Kubernetes API via the Agent Space EKS access entry (read-only). No Bash, no kubectl, no MCP. |
| Kubernetes API access | `kubectl` against local kubeconfig, or MCP `list_k8s_resources` | EKS Access Entry binding the Agent Space role to `AmazonAIOpsAssistantPolicy` (cluster scope); expressed in references as "**Via Kubernetes API**" capability blocks, not `kubectl` pipelines |
| Subagent orchestration | 10 module subagents spawned in parallel via the Agent tool (`agents/*.md`) | No Agent tool — collapsed into SKILL.md reference-loading. Each module is a `references/<module>.md` file loaded on demand via the routing table. |
| Report generation | Markdown fact report + YAML artifact, written to `<output-prefix>.{md,yaml}`; caller-supplied prefix honored, default `EKS-Recon-<cluster>-<YYYY-MM-DD>-<HHMM>` | Markdown primary + YAML snapshot, fixed UTC timestamped names; no caller prefix. Named-destination collision checks only when supported by the service; no filesystem APIs assumed |
| Prior-run comparison | Optional caller-selected YAML path; facts-only delta; collision prompts for a new prefix after showing facts inline | Optional accessible YAML content/attachment; same fact-comparison semantics, but collision returns an error without prompting; facts remain inline |
| Script dependencies | Python 3 for the GitOps metadata extractor ([invocation](../../../skills/eks-recon/references/cicd.md#spoke-side-tracking-and-the-gitops-outcome)) | None — no scripts permitted |
| Cluster selection | Auto-discovers, asks user on ambiguity | Auto-selects single cluster; assesses all discovered on ambiguity; HARD STOP on API failure / zero clusters |
| MCP dependencies | References eks-mcp-server for richer live data | No MCP dependencies; uses Agent Space APIs directly |
| iac `evidence.type` enum | 4 values (upstream Output Schema): includes `workspace_files` and `cfn_stacks` | 2 values (port Output Schema): `cluster_tags` \| `in_cluster_crds`. Drops `workspace_files` (no filesystem in Agent Space) and `cfn_stacks` (the port's `iam-policy.json` grants no `cloudformation:*` permission). CloudFormation cluster-tag evidence remains available via `aws:cloudformation:*` tags → `cluster_tags` evidence + `tags.cfn_stack_id`; stack API observations are unavailable in the port. |

GitOps workload reads require projection before tool output reaches the model.
Without it, both spoke-side tracking and controller inspection are unavailable;
report those Coverage gaps. The API port has no shell fallback.

## Access-entry mechanism (why iam-policy.json has no `eks:AccessKubernetesApi`)

The DevOps Agent reaches the Kubernetes API through an **EKS Access Entry** that binds the Agent Space role to the AWS-managed `AmazonAIOpsAssistantPolicy` cluster-access policy (cluster scope), provisioned by `devops-agent/setup.sh`. The cluster's `authenticationMode` must include `API` (i.e. `API` or `API_AND_CONFIG_MAP`). Because the access entry — not an IAM action — grants K8s-API **authentication**, `iam-policy.json` contains **only AWS control-plane reads** and deliberately omits `eks:AccessKubernetesApi`.

**Authorization is narrower than authentication, and the two must not be conflated.** The access entry only authenticates the role; `AmazonAIOpsAssistantPolicy` supplies the RBAC, and it authorizes read-only `get`/`list` on **built-in API groups only** — core, `apps`, `batch`, `events.k8s.io`, `networking.k8s.io`, `storage.k8s.io`, and `metrics.k8s.io`. It grants **no CRD groups** (not even `apiextensions.k8s.io`). Consequently CRD-based facts (Karpenter `NodePool`/`EC2NodeClass`, Auto Mode `NodeClass`, Velero, `TargetGroupBinding`, VPA, policy engines, service mesh, GitOps, Crossplane/ACK) are **not** readable through the access entry alone — those reads return `403 Forbidden`. Capturing them requires binding the role to a **supplementary read-only ClusterRole** (or a broader access policy) granting `get`/`list` on the relevant CRD groups. Absent that, CRD-dependent sub-facts degrade to `unconfirmed` in the report's Coverage section — never `false`/`count: 0`. (See SKILL.md for the authoritative RBAC breakdown.)
