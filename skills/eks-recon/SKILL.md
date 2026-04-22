---
name: eks-recon
description: EKS cluster reconnaissance and environment discovery. Detects compute strategy (Karpenter, MNG, Auto Mode, Fargate), IaC tooling (Terraform, CloudFormation, CDK, eksctl), CI/CD pipelines (GitHub Actions, GitLab, ArgoCD, Flux), add-on inventory, networking, security posture, and observability. Use this skill whenever someone asks about their EKS cluster, wants to understand their setup, is planning an upgrade or migration, needs cluster context for any reason, asks "what version am I running", mentions wanting to review or document their cluster, or is about to make any EKS-related decision - even if they don't explicitly say "reconnaissance" or "discovery". When in doubt about cluster state, run recon first.
---

# EKS Reconnaissance

Discover everything about an EKS cluster environment. Run this skill to gather comprehensive cluster context before making any decisions, changes, or recommendations.

## When to Use This Skill

**Run this skill when the user:**
- Asks about their EKS cluster ("what's my cluster running?", "tell me about my setup")
- Plans an upgrade, migration, or architecture change
- Needs cluster context before any EKS-related decision
- Wants to document or review their cluster state
- Asks questions like "what version am I on?" or "am I using Karpenter?"
- Is about to modify their cluster (recon first to understand current state)

**Also trigger this skill when:**
- User mentions an EKS cluster name and seems to need context
- Another workflow needs cluster information as input
- You need to understand the cluster before giving recommendations

**Don't use for:**
- Creating or modifying cluster resources (this is read-only)
- Troubleshooting specific issues (use `eks-best-practices` or `eks-upgrader`)
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

1. **Grant MCP access**: Create an EKS access entry for the MCP server's IAM role
   ```bash
   aws eks create-access-entry \
     --cluster-name <cluster> \
     --principal-arn <mcp-server-role-arn> \
     --type STANDARD
   aws eks associate-access-policy \
     --cluster-name <cluster> \
     --principal-arn <mcp-server-role-arn> \
     --policy-arn arn:aws:eks::aws:cluster-access-policy/AmazonEKSViewPolicy \
     --access-scope type=cluster
   ```

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

## Reference Loading Strategy

Load only the reference files needed for the user's request. This keeps context focused and improves response quality.

### Decision Matrix

| If user mentions... | Load these references |
|---------------------|----------------------|
| Karpenter, nodes, scaling, compute, Auto Mode, node groups | cluster-basics.md, compute.md |
| Networking, VPC, ingress, CNI, service mesh, load balancer | cluster-basics.md, networking.md |
| Security, IAM, IRSA, Pod Identity, RBAC, policies, encryption | cluster-basics.md, security.md |
| Add-ons, Helm, plugins, what's installed | cluster-basics.md, addons.md |
| Logging, metrics, monitoring, observability, Container Insights | cluster-basics.md, observability.md |
| Workloads, deployments, pods, services, what's running | cluster-basics.md, workloads.md |
| Terraform, IaC, CloudFormation, CDK, eksctl, how is it managed | iac.md |
| CI/CD, pipelines, GitOps, ArgoCD, Flux, GitHub Actions | cicd.md |
| Full recon, deep dive, comprehensive, everything, all modules | ALL references |

### Loading Rules

1. **`cluster-basics.md` is always loaded first** — provides cluster context needed by all modules
2. **For targeted queries** — load only the matching reference(s) from the matrix
3. **For full recon** — load all references in parallel
4. **When uncertain** — ask the user which aspects they want to explore, or default to full recon

---

## Available Modules

Each module is a reference file that can be run independently. Load the reference when running that module.

| Module | Reference | What It Detects | Cluster Required |
|--------|-----------|-----------------|------------------|
| **Cluster Basics** | [cluster-basics.md](references/cluster-basics.md) | Name, region, version, platform version, endpoint | Yes |
| **Compute** | [compute.md](references/compute.md) | Karpenter, MNG, Auto Mode, Fargate, self-managed | Yes |
| **IaC** | [iac.md](references/iac.md) | Terraform, CloudFormation, CDK, eksctl, Pulumi | No (workspace) |
| **CI/CD** | [cicd.md](references/cicd.md) | GitHub Actions, GitLab CI, Jenkins, ArgoCD, Flux | Partial |
| **Add-ons** | [addons.md](references/addons.md) | EKS-managed, Helm releases, manifest-installed | Yes |
| **Networking** | [networking.md](references/networking.md) | VPC CNI, ingress controllers, service mesh | Yes |
| **Security** | [security.md](references/security.md) | Pod Identity, IRSA, PSA, policy engines | Yes |
| **Observability** | [observability.md](references/observability.md) | Container Insights, Prometheus, logging config | Yes |
| **Workloads** | [workloads.md](references/workloads.md) | Running deployments, services, ingresses | Yes |

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
| Node groups | `aws eks list-nodegroups --cluster-name <name>` |
| EKS add-ons | `aws eks list-addons --cluster-name <name>` |
| Fargate profiles | `aws eks list-fargate-profiles --cluster-name <name>` |
| Auto Mode | `aws eks describe-cluster --name <name> --query 'cluster.computeConfig'` |
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
- Cluster name
- AWS region (or detect from context/kubeconfig)

Optional:
- Specific modules to run (default: all)
- Output file path (default: .eks-recon-report.yaml)
```

### Step 2: Check MCP Availability

If MCP tools are available, use them. Otherwise, inform the user:

> "EKS MCP Server not detected. I'll use CLI commands instead, which will require your permission for each command. For a smoother experience, consider setting up the EKS MCP Server."

### Step 3: Run Selected Modules

Determine which modules to run based on user intent (see [Reference Loading Strategy](#reference-loading-strategy)).

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

Write report to `.eks-recon-report.yaml` and present summary:

```yaml
# EKS Reconnaissance Report
# Generated: 2026-04-22T14:30:00Z
# Cluster: my-cluster
# Region: us-west-2
# Modules: cluster-basics, compute, iac, cicd, addons

cluster:
  name: my-cluster
  region: us-west-2
  version: "1.31"
  platform_version: eks.5
  endpoint: https://XXXXX.gr7.us-west-2.eks.amazonaws.com
  
compute:
  strategy: Karpenter
  auto_mode:
    enabled: false
  karpenter:
    detected: true
    version: "1.0.5"
    nodepools: 2
  mng:
    detected: true
    count: 1
    names: [system]
  fargate:
    detected: false
    
iac:
  tool: Terraform
  confidence: high
  evidence: "./infrastructure/eks/main.tf contains aws_eks_cluster"
  
cicd:
  workspace:
    - github_actions
  gitops:
    tool: ArgoCD
    detected: true
    namespace: argocd
    
addons:
  eks_managed:
    - name: vpc-cni
      version: v1.18.1-eksbuild.1
      status: ACTIVE
    - name: coredns
      version: v1.11.1-eksbuild.8
      status: ACTIVE
  helm_releases:
    - name: karpenter
      namespace: kube-system
      version: 1.0.5
```

---

## Subagent Mode

When running full reconnaissance, delegate each module to a specialized subagent. This keeps each module's context isolated and enables true parallel execution.

### When to Use Subagents

| Scenario | Mode | Reason |
|----------|------|--------|
| Any recon (1+ modules) | **USE subagents** | Isolated context, cleaner main conversation |
| No Agent tool available | Inline | Subagents not supported |

> **IMPORTANT:** If the Agent tool is available, you MUST use subagent mode for ALL reconnaissance — even single-module targeted queries. Subagents keep detection context isolated from the main conversation. Do not fall back to inline mode just because "it's only one module" or "MCP tools work" — always delegate to subagents.

### Subagent Files

Each module has a corresponding subagent prompt in `agents/`:

| Subagent | File | Purpose |
|----------|------|---------|
| Compute | `agents/compute-recon.md` | Detect compute strategy |
| Networking | `agents/networking-recon.md` | Detect network config |
| Security | `agents/security-recon.md` | Detect security posture |
| Add-ons | `agents/addons-recon.md` | Detect installed components |
| Observability | `agents/observability-recon.md` | Detect monitoring/logging |
| Workloads | `agents/workloads-recon.md` | Detect running workloads |
| IaC | `agents/iac-recon.md` | Detect IaC tooling |
| CI/CD | `agents/cicd-recon.md` | Detect deployment pipelines |

### Orchestration Steps

**Step 1: Check subagent availability**
```
If Agent tool is available:
  → MUST use subagent mode for ALL recon (full or targeted)
  → Even single-module queries use subagents to isolate context
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

... (spawn all 8 in parallel)
```

**Step 3: Aggregate results**

When all subagents complete:
1. Collect each subagent's YAML output
2. Merge into single report structure
3. Add cross-module insights (e.g., "Karpenter detected but no IRSA for controller")
4. Generate recommendations based on combined findings
5. Write final report to `.eks-recon-report.yaml`
6. Present summary to user

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

---

## Detailed References

Load the appropriate reference file when running each module. Each reference contains detection commands, edge cases, and output schema for that domain.

| Reference | Load When... |
|-----------|--------------|
| **[Cluster Basics](references/cluster-basics.md)** | Starting any recon (always load first) |
| **[Compute](references/compute.md)** | User asks about nodes, scaling, Karpenter, Auto Mode, or upgrade planning |
| **[IaC](references/iac.md)** | User asks how the cluster is managed, wants to make changes via IaC, or is troubleshooting state drift |
| **[CI/CD](references/cicd.md)** | User asks about deployments, pipelines, GitOps, or how changes get applied |
| **[Add-ons](references/addons.md)** | Upgrade planning, compatibility checks, or user asks "what's installed?" |
| **[Networking](references/networking.md)** | User asks about connectivity, ingress, service mesh, or network troubleshooting |
| **[Security](references/security.md)** | User asks about IAM, IRSA, Pod Identity, policies, or compliance review |
| **[Observability](references/observability.md)** | User asks about logging, metrics, monitoring, or troubleshooting visibility |
| **[Workloads](references/workloads.md)** | User wants to see what's running, capacity planning, or migration assessment |
