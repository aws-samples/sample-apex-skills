---
title: "eks-recon"
description: "EKS cluster reconnaissance and environment discovery — reports the raw FACTS of a cluster and its environment. Detects compute (Karpenter, MNG, Auto Mode, Fargate, nodes/AMI), networking (VPC/CNI, subnets, load balancers, DNS), security facts (auth mode, IRSA/Pod Identity, RBAC, encryption), add-ons/Helm, observability, workloads (Deployments, StatefulSets, PDBs, HPAs), storage (CSI, StorageClasses, PVs, backup tooling), IaC (Terraform, CDK, eksctl), CI/CD (Actions, ArgoCD, Flux), and cluster insights. Use to discover or document the current state of an EKS cluster — 'what am I running', 'tell me about my setup', 'what version am I on', inventory before an upgrade/migration/design. Reports facts only; it does not score, rate, plan, or recommend, and overlapping facts with other skills is fine. Route elsewhere for a JUDGMENT or ARTIFACT: readiness scoring/deprecated-API checks (eks-upgrade-check), GREEN/AMBER/RED audits (eks-operation-review), design docs/diagrams (eks-design)."
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-recon/SKILL.md
format: md
---

:::info[Source]
This page is generated from [skills/eks-recon/SKILL.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/eks-recon/SKILL.md). Edit the source, not this page.
:::


# EKS Reconnaissance

Discover everything about an EKS cluster environment. Run this skill to gather comprehensive cluster context before making any decisions, changes, or recommendations.

## When to Use This Skill

**Run this skill when the user wants to discover or document cluster FACTS:**
- Asks about their EKS cluster ("what's my cluster running?", "tell me about my setup")
- Wants an inventory of current state before an upgrade, migration, or architecture change
- Wants to document or review what exists in their cluster
- Asks questions like "what version am I on?" or "am I using Karpenter?"

**Also trigger this skill when:**
- User mentions an EKS cluster name and seems to need its current-state facts
- Another workflow needs raw cluster facts as input

Recon reports **facts only**. Reporting facts that also matter to another skill (upgrade, security, design) is expected and fine — the dividing line is discovery-of-facts (here) vs. verdict/score/artifact (route elsewhere, below).

**Do NOT use this skill for:**
- **Upgrade readiness scoring or deprecated API checks** — questions like "score my upgrade readiness", "are there deprecated APIs blocking my upgrade", "can I safely upgrade to 1.33", "readiness score", or "breaking changes that would block a version bump" belong to `eks-upgrade-check`. Recon discovers *what version you're on*; it does NOT assess whether you're *ready* to move to the next version.
- **Operational audits with maturity ratings** — questions like "run an operational excellence audit", "rate each area GREEN/AMBER/RED", or "audit my cluster's operational posture" belong to `eks-operation-review`. Recon inventories what exists; it does NOT score operational maturity or produce rated assessments.
- **Architecture design documents or Mermaid diagrams** — questions like "create a security architecture document", "generate Mermaid diagrams for our EKS cluster", or "design document" belong to `eks-design`. Recon discovers current state; it does NOT produce design artifacts or architectural diagrams.
- Creating or modifying cluster resources (this is read-only)
- Troubleshooting specific issues (use `eks-best-practices`)
- Learning about EKS concepts (use `eks-best-practices`)

## Prerequisites

### MCP Server (Preferred)

This skill works best with the **EKS MCP Server** configured. Check if MCP tools are available:

```
If tools like `list_eks_resources`, `describe_eks_resource`, `list_k8s_resources` are available:
  -> MCP Mode: Use MCP tools (pre-authorized, richer output)
  
If MCP tools are NOT available:
  -> CLI Mode: Fall back to AWS CLI + kubectl (requires explicit permission)
```

**MCP Mode benefits:**
- Pre-authorized read-only operations (no permission prompts)
- Richer output with better formatting
- Single tool call instead of piped commands

**CLI Mode limitations:**
- Requires user permission for each command
- May need kubeconfig setup
- Some detection patterns are less reliable

### Required for CLI Mode

| Tool | Required For |
|------|-------------|
| `aws` CLI | Cluster-level detection (describe-cluster, list-nodegroups, list-addons) |
| `kubectl` | K8s resource detection (deployments, CRDs, service accounts) |
| `helm` | Helm release inventory (optional) |

### MCP Troubleshooting

**401 Unauthorized on K8s API calls** (`list_k8s_resources`, `read_k8s_resource`):

The MCP server can access EKS APIs (clusters, nodegroups, addons) but may lack Kubernetes API access. This happens when the MCP server's IAM role doesn't have an EKS access entry.

**Solutions (choose one):**

1. **Grant MCP access**: Create an EKS access entry for the MCP server's IAM role.

   **Surface these commands to the user — do NOT execute them. These are persistent IAM writes and violate the read-only contract of this skill.**

   ```bash
   aws eks create-access-entry \
     --cluster-name <cluster> \
     --region <region> \
     --principal-arn <mcp-server-role-arn> \
     --type STANDARD
   aws eks associate-access-policy \
     --cluster-name <cluster> \
     --region <region> \
     --principal-arn <mcp-server-role-arn> \
     --policy-arn arn:aws:eks::aws:cluster-access-policy/AmazonEKSViewPolicy \
     --access-scope type=cluster
   ```

   If the user confirms and has permission, they can run these themselves out-of-band.

2. **Fall back to kubectl**: If user has local kubectl access, use CLI commands instead:
   > "MCP K8s access returned 401. I'll use kubectl instead if you have it configured locally."

**Empty results from EKS API calls**:
- Verify cluster name and region are correct
- Check if the cluster exists: `aws eks list-clusters --region <region>`

---

## Reconnaissance Modes

| Mode | When to Use | What Happens |
|------|-------------|--------------|
| **Full Recon** | First engagement with cluster | Runs all modules, generates complete report |
| **Selective Recon** | Know what you need | Run specific modules (e.g., compute + iac) |
| **Targeted Query** | Quick answer | "Is this cluster using Karpenter?" |

### How to Invoke

**Full reconnaissance:**
> "Run EKS reconnaissance on cluster `my-cluster` in `us-west-2`"

**Selective reconnaissance:**
> "Run EKS recon but only check compute and IaC"

**Targeted query:**
> "What IaC tool manages cluster `my-cluster`?"

---

## Modules and Reference Loading

Load only the references needed for the user's request — this keeps context focused. `references/cluster-basics.md` is **always loaded first** by every module; it provides the shared cluster context all other modules depend on. For targeted queries, load only the matching row(s); for full recon, load all references in parallel. When uncertain, ask the user or default to full recon.

| Module | Intent / when to use | Reference file | Agent file |
|--------|----------------------|----------------|------------|
| Cluster Basics | Always loaded first by every module (name, region, version, platform version, endpoint) | [cluster-basics.md](references/cluster-basics) | — |
| Compute | Karpenter, nodes, scaling, Auto Mode, node groups, Fargate, self-managed | [compute.md](references/compute) | [compute-recon.md](agents/compute-recon) |
| Networking | VPC, ingress, CNI, service mesh, load balancer, connectivity | [networking.md](references/networking) | [networking-recon.md](agents/networking-recon) |
| Security | IAM, IRSA, Pod Identity, RBAC, policies, encryption, secrets, webhooks | [security.md](references/security) | [security-recon.md](agents/security-recon) |
| Add-ons | EKS-managed add-ons, Helm releases, plugins, "what's installed?" | [addons.md](references/addons) | [addons-recon.md](agents/addons-recon) |
| Observability | Logging, metrics, monitoring, Container Insights, Prometheus | [observability.md](references/observability) | [observability-recon.md](agents/observability-recon) |
| Workloads | Deployments, pods, services, ingresses, "what's running?" | [workloads.md](references/workloads) | [workloads-recon.md](agents/workloads-recon) |
| Storage | PVCs, EBS, EFS, StorageClasses, CSI drivers, volumes, snapshots | [storage.md](references/storage) | [storage-recon.md](agents/storage-recon) |
| IaC | Terraform, CloudFormation, CDK, eksctl, Pulumi, "how is it managed?" | [iac.md](references/iac) | [iac-recon.md](agents/iac-recon) |
| CI/CD | GitHub Actions, GitLab CI, Jenkins, ArgoCD, Flux, GitOps, pipelines | [cicd.md](references/cicd) | [cicd-recon.md](agents/cicd-recon) |
| Cluster Insights | EKS-reported upgrade-readiness & configuration insights (raw findings) | [cluster-insights.md](references/cluster-insights) | [cluster-insights-recon.md](agents/cluster-insights-recon) |

---

## Quick Detection Reference

### MCP Commands (Preferred)

| Detection | MCP Tool |
|-----------|----------|
| Cluster info | `describe_eks_resource(resource_type="cluster", cluster_name="<name>")` |
| Node groups | `list_eks_resources(resource_type="nodegroup", cluster_name="<name>")` |
| EKS add-ons | `list_eks_resources(resource_type="addon", cluster_name="<name>")` |
| Karpenter | `list_k8s_resources(cluster_name="<name>", kind="NodePool", api_version="karpenter.sh/v1")` |
| Deployments | `list_k8s_resources(cluster_name="<name>", kind="Deployment", api_version="apps/v1")` |
| VPC config | `get_eks_vpc_config(cluster_name="<name>")` |
| Insights | `get_eks_insights(cluster_name="<name>")` |

### CLI Fallbacks

| Detection | CLI Command |
|-----------|-------------|
| Cluster info | `aws eks describe-cluster --name <name> --region <region>` |
| Node groups | `aws eks list-nodegroups --cluster-name <name> --region <region>` |
| EKS add-ons | `aws eks list-addons --cluster-name <name> --region <region>` |
| Fargate profiles | `aws eks list-fargate-profiles --cluster-name <name> --region <region>` |
| Auto Mode | `aws eks describe-cluster --name <name> --region <region> --query 'cluster.computeConfig'` |
| Karpenter | `kubectl get nodepools.karpenter.sh 2>/dev/null` |
| Helm releases | `helm list -A` |

---

## Running Reconnaissance

> **IMPORTANT: Load Reference Files**
> 
> Before running each module, you MUST read its reference file (e.g., `references/compute.md`).
> References contain:
> - Detection order and rationale (why check Auto Mode before Karpenter)
> - Edge cases and how to handle them
> - CLI fallback commands when MCP fails
> - Output schema for structured reporting
> 
> Skipping references produces shallow results. The main skill provides orchestration;
> the references provide detection intelligence.

### Step 1: Gather Prerequisites

```
Required:
- Cluster name (or auto-discover — see below)
- AWS region (or detect from context/kubeconfig/CLI)

Optional:
- Specific modules to run (default: all)
- Output path prefix (default: `.eks-recon-report` → writes `.eks-recon-report.md` + `.eks-recon-report.yaml`)
```

**Auto-discovery when cluster name is not explicit:**

When the user says "my cluster", "current cluster", or does not name a specific cluster, discover it:

1. `kubectl config current-context` — if set, extract cluster name from the context ARN
2. If no kubeconfig context, try **AWS CLI directly** (credentials may come from `~/.aws/` config files, instance profile, or env vars — don't assume env vars are the only source):
   ```bash
   aws sts get-caller-identity  # verify we have working AWS access
   aws eks list-clusters --region ${AWS_DEFAULT_REGION:-us-west-2}
   ```
3. If exactly one cluster is found, use it. If multiple clusters across regions, try common regions (us-west-2, us-east-1, the region in any ARN visible in kubeconfig).
4. Only ask the user to specify a cluster if discovery yields multiple candidates and the prompt is ambiguous.

**IMPORTANT:** Never give up after checking only environment variables. AWS credentials can come from `~/.aws/credentials`, `~/.aws/config`, instance metadata, or ECS task roles — none of which appear in `env | grep AWS_`. Always try `aws sts get-caller-identity` before concluding credentials are unavailable.

**IMPORTANT — verify the kubectl context matches the TARGET cluster.** When the user names a specific cluster, do NOT assume `kubectl config current-context` points at it — the current context frequently points at a *different* cluster (even a different region). Before running any kubectl detection, confirm the active context resolves to the named cluster (compare the context's cluster ARN/endpoint, or run `aws eks update-kubeconfig --name <cluster> --region <region>` to bind kubectl to the intended cluster, then `--context <that-context>`). Reconning the wrong cluster silently produces a confident-but-wrong report. If you cannot confirm the context maps to the named cluster, say so rather than proceeding against an unverified context.

### Step 2: Check MCP Availability

If MCP tools are available, use them. Otherwise, inform the user:

> "EKS MCP Server not detected. I'll use CLI commands instead, which will require your permission for each command. For a smoother experience, consider setting up the EKS MCP Server."

### Step 3: Run Selected Modules

Determine which modules to run based on user intent (see [Modules and Reference Loading](#modules-and-reference-loading)).

For each selected module:
1. **Load the reference file** (e.g., `references/compute.md`) - REQUIRED
   - For targeted queries: load only the required reference(s) per decision matrix
   - For full recon: load all references in parallel
2. Run detection commands following the reference's guidance:
   - Try MCP tool first
   - If MCP returns error (401, empty), fall back to CLI from reference
   - If CLI unavailable, note the limitation in report
3. Collect output into report section using the reference's output schema

### Step 4: Generate Report

Produce **two** artifacts. The **markdown fact report is the primary deliverable** (rendered inline to the user); the YAML is a machine artifact for optional hand-off to other skills.

> **Facts only.** Both artifacts report what the cluster *is*. Never emit a verdict, score, readiness rating, or recommendation. A "Notable facts" line states an observation ("2 subnets have < 16 free IPs"); it never says "you should" or "this is a risk".

#### 4a. Markdown fact report (primary) → `.eks-recon-report.md`

Render this structure, including **only modules that actually ran**:

```markdown
# EKS Recon — <cluster> (<region>)
_generated <timestamp> · source: MCP | CLI · modules: N/N_

## Cluster summary
| Fact | Value |
|------|-------|
| version / platform | 1.31 / eks.5 |
| support type | STANDARD |
| status / created | ACTIVE / 2024-09-10 |
| authentication mode | API_AND_CONFIG_MAP |
| compute strategy | Karpenter + 1 MNG |
| IaC | Terraform (high confidence) |
| CI/CD | GitHub Actions + ArgoCD |

## Per-module facts
### Compute
<small fact table per module — one H3 per RUN module>
### Networking
...

## Notable facts
<flat bullets: co-occurring or absent facts, stated neutrally, ZERO verdicts>
- authentication_mode = API_AND_CONFIG_MAP; aws-auth ConfigMap present
- compute.strategy = Karpenter; security.iam_for_pods.irsa.detected = false
- 2 of 4 cluster subnets report < 16 available IPs

## Coverage
<modules that could not run + reason, AND sub-facts that ran but could not be confirmed — makes gaps visible>
- storage: unavailable (reason: MCP 401 and kubectl not configured)
- addons.helm_releases: unconfirmed (reason: helm CLI absent, secret fallback not run) — reported as `unconfirmed`, not `count: 0`

## Machine artifact
- `.eks-recon-report.yaml` written (canonical schema, for hand-off to other skills)
```

#### 4b. Machine YAML artifact → `.eks-recon-report.yaml`

Assemble one top-level key per module, each emitted **verbatim in the canonical shape defined by that module's `references/<module>.md` "## Output Schema"**, plus the shared `cluster:` block and the `cluster_detail:` block (both from `references/cluster-basics.md`). Unavailable modules become `<module>: {unavailable: true, reason: "<short reason>"}`.

> **The reference Output Schemas are the single source of truth for the YAML shape** — do not hand-copy a schema here (that is how the old example drifted). The illustrative fragment below shows only the envelope; the authoritative per-module shape lives in each reference.

```yaml
# EKS Reconnaissance Report — illustrative envelope only.
# Canonical shape per module = references/<module>.md "## Output Schema".
cluster:              # shape: references/cluster-basics.md "## Shared Cluster Block"
  name: my-cluster
  region: us-west-2
  version: "1.31"
  platform_version: eks.5
  status: ACTIVE
  tags: {team: platform}
cluster_detail:       # shape: references/cluster-basics.md "## Cluster Detail (full recon)"
  upgrade_policy: {support_type: STANDARD}
  # ...zonal_shift.enabled, certificate_authority.present, health.issues, encryption_config
compute:              # shape: references/compute.md "## Output Schema"
  strategy: Karpenter
  # ...every field the reference schema defines, null where undetected
networking: { ... }   # shape: references/networking.md
# ...one key per module that ran; unavailable modules:
storage:
  unavailable: true
  reason: "MCP 401 and kubectl not configured"
```

---

## Subagent Mode

When running full reconnaissance, delegate each module to a specialized subagent. This keeps each module's context isolated and enables true parallel execution.

### When to Use Subagents

| Scenario | Mode | Reason |
|----------|------|--------|
| Full or multi-module recon | **USE subagents** | Isolated context, true parallel execution across modules |
| Single-module targeted query | **Inline preferred** | One reference, one detection — a subagent spawn adds a full model turn for a one-line answer |
| No Agent tool available | Inline | Subagents not supported |

> **IMPORTANT:** If the Agent tool is available, use subagent mode for **full or multi-module** reconnaissance — one subagent per module, spawned in parallel — so each module's detection context stays isolated. For a **single-module targeted query** (e.g. "Is this cluster using Karpenter?"), inline is preferred: load the one reference and run detection directly. Escalate a targeted query to a subagent only if it fans out to 2+ modules or the raw tool output would flood the main context.

### Subagent Files

Each module has a corresponding subagent prompt in `agents/`:

| Subagent | File | Purpose |
|----------|------|---------|
| Compute | `agents/compute-recon.md` | Detect compute strategy |
| Networking | `agents/networking-recon.md` | Detect network config |
| Security | `agents/security-recon.md` | Detect security posture, secrets, webhooks |
| Add-ons | `agents/addons-recon.md` | Detect installed components |
| Observability | `agents/observability-recon.md` | Detect monitoring/logging |
| Storage | `agents/storage-recon.md` | Detect CSI, StorageClasses, PVCs |
| Workloads | `agents/workloads-recon.md` | Detect running workloads |
| IaC | `agents/iac-recon.md` | Detect IaC tooling |
| CI/CD | `agents/cicd-recon.md` | Detect deployment pipelines |
| Cluster Insights | `agents/cluster-insights-recon.md` | Collect EKS-reported insights (raw findings) |

### Orchestration Steps

**Step 1: Check subagent availability**
```
If Agent tool is available:
  → Full or multi-module recon → use subagent mode (one subagent per module, in parallel)
  → Single-module targeted query → inline is preferred (load the one reference, detect directly)
Else:
  → Use inline mode (load references directly)
```

**Step 2: Spawn module subagents in parallel**

Spawn ALL module subagents in a SINGLE message for parallel execution:

```
Agent(
  description: "EKS compute recon",
  prompt: "Recon compute for cluster {cluster_name} in {region}. 
           Read agents/compute-recon.md and references/compute.md.
           Return YAML output only.",
  subagent_type: "general-purpose"
)

Agent(
  description: "EKS networking recon",
  prompt: "Recon networking for cluster {cluster_name} in {region}.
           Read agents/networking-recon.md and references/networking.md.
           Return YAML output only.",
  subagent_type: "general-purpose"
)

... (spawn every selected module's subagent in parallel — up to all 10)
```

**Step 3: Aggregate results**

When all subagents complete:
1. Collect each subagent's YAML output
2. Merge into single report structure, applying these normalization rules:
   - Every subagent emits its own top-level `cluster:` block. Merge into a single top-level `cluster:` by deduplicating exact-match blocks (all subagents report the same cluster); if any field mismatches across subagents, flag it rather than silently picking one.
   - **`cluster-basics` has no subagent** — it is always-loaded shared context. Beyond the shared `cluster:` block, it also owns the top-level **`cluster_detail:`** facts (support_type, zonal_shift, certificate_authority, health, encryption_config — see `references/cluster-basics.md` "## Cluster Detail (full recon)"). On a full recon, run those cluster-basics detection commands directly (inline, from the main thread — they are a handful of `describe-cluster` reads) and merge the result as the top-level `cluster_detail:` key. Skip on a targeted query that doesn't need them.
   - Module outputs are already in the canonical shape defined by each `references/<module>.md` "## Output Schema". Preserve them verbatim under the matching top-level key: `compute:`, `networking:`, `security:`, `addons:`, `observability:`, `workloads:`, `storage:`, `iac:`, `cicd:`, `cluster_insights:`. Do not reshape, flatten, or rename keys.
   - If a subagent fails to respond or errors out, set its key to `unavailable: true` with a short `reason:` string; do not omit the key.
3. Note co-occurring or absent facts across modules — state the observation, draw no conclusion (e.g. "compute.strategy = Karpenter; security.iam_for_pods.irsa.detected = false"). These are neutral facts for the "Notable facts" section, never verdicts or recommendations.
4. Render the **human-readable markdown fact report** (primary) and write the **machine YAML artifact** — see [Step 4](#step-4-generate-report).

---

## Integration with Other Workflows

### Upgrade Workflow

The upgrade workflow can invoke eks-recon to gather Phase 1 context:

```
1. Run eks-recon modules: cluster-basics, compute, iac, addons
2. Extract:
   - cluster.version -> Current version
   - compute.strategy -> Determines upgrade approach
   - iac.tool -> Terraform vs CLI upgrade path
   - addons -> Compatibility matrix input
```

### Design Workflow

The design workflow can use eks-recon for existing clusters:

```
1. Run eks-recon modules: all
2. Pre-populate questionnaire from detected values
3. Ask user: "I detected Karpenter + Terraform + ArgoCD. Correct?"
4. Only ask questions for undetected values
```

