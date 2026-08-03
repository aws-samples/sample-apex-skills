---
title: "EKS Upgrade Readiness — AWS DevOps Agent Skill"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/devops-agent/eks-upgrade-check/references/porting-notes.md
format: md
---

:::info[Source]
This page is generated from [devops-agent/eks-upgrade-check/references/porting-notes.md](https://github.com/aws-samples/sample-apex-skills/blob/main/devops-agent/eks-upgrade-check/references/porting-notes.md). Edit the source, not this page.
:::

# EKS Upgrade Readiness — AWS DevOps Agent Skill

This folder is an [AWS DevOps Agent](https://docs.aws.amazon.com/devopsagent/latest/userguide/) compatible port of the EKS Upgrade Readiness skill from the parent repository (originally built as a Claude Code skill).

It follows the [Agent Skills specification](https://agentskills.io/) subset that AWS DevOps Agent supports: non-executable documents only (Markdown instructions, data files) organized around a required `SKILL.md`.

## Structure

```
DevOpsAgent/
├── SKILL.md                     # Required: frontmatter (name + description) + workflow
├── references/                  # Assessment logic (loaded on demand by the agent)
│   ├── version-validation.md
│   ├── breaking-changes.md
│   ├── deprecated-apis.md
│   ├── addon-compatibility.md
│   ├── node-readiness.md
│   ├── workload-risks.md
│   ├── upgrade-insights.md
│   └── report-generation.md
└── assets/
    └── oss_addon_registry.json  # OSS add-on identifiers + authoritative upstream URLs
```

## What the skill does

Assesses a live EKS cluster's readiness for a Kubernetes version upgrade across 8 areas, calculates a readiness score (0–100%), and generates a report with prioritized remediation and pre-filled AWS CLI commands. All operations are **read-only**.

See [`SKILL.md`](../) for the full assessment workflow.

## How to install into an Agent Space

**Option A — Import from repository (recommended)**

1. In the Agent Space Operator Web App, go to **Knowledge → Skills → Add skill → Import from repository**.
2. Enter the GitHub directory URL pointing at this folder (the directory containing `SKILL.md`).
3. Select the agent type(s). **On-demand** is a good fit for a user-invoked assessment; **Generic** makes it available to all agent types.

**Option B — Upload as a zip**

1. From **inside** this `DevOpsAgent/` folder, first copy the repository `LICENSE` in so it ships inside the zip, then zip the contents so that `SKILL.md` sits at the zip root:

   ```bash
   cp ../LICENSE ./LICENSE
   zip -r ../eks-upgrade-check-skill.zip .
   ```

   This drops `eks-upgrade-check-skill.zip` in the parent directory.

2. Verify the contents before uploading — `SKILL.md` should appear with no directory prefix:

   ```bash
   unzip -l ../eks-upgrade-check-skill.zip
   ```

   Expected (abbreviated):

   ```
   SKILL.md
   README.md
   references/version-validation.md
   references/...
   assets/oss_addon_registry.json
   ```

3. In the Operator Web App, go to **Knowledge → Skills → Add skill → Upload skill** and upload the zip (ZIP only, ≤ 6 MB).

## Prerequisites

The DevOps Agent IAM role must have access to each EKS cluster you want to assess. In
order for the agent to run the full upgrade assessment, the cluster access permissions
must be updated beyond the default setup — follow the steps below for each cluster.

**Official guide:** [Configuring EKS access for DevOps Agent](https://docs.aws.amazon.com/devopsagent/latest/userguide/configuring-integrations-and-knowledge-aws-eks-access-setup.html)

In all commands below, replace:

- `<CLUSTER>` — your EKS cluster name
- `<REGION>` — the cluster's AWS region
- `<DEVOPS_AGENT_ROLE_ARN>` — the Agent Space IAM role ARN, e.g.
  `arn:aws:iam::111122223333:role/service-role/DevOpsAgentRole-AgentSpace-abc123`
  (find it in the DevOps Agent console under **Agent Space → Capabilities → Cloud →
  Primary source → Edit**)

### Step 1: Create the access entry

Ensure the cluster authentication mode includes **EKS API** (`API` or
`API_AND_CONFIG_MAP`) — check the **Access** tab in the EKS console.

**If the role has no access entry yet** (a fresh setup), run both commands:

```bash
aws eks create-access-entry \
  --cluster-name <CLUSTER> \
  --region <REGION> \
  --type STANDARD \
  --kubernetes-groups eks-upgrade-check \
  --principal-arn <DEVOPS_AGENT_ROLE_ARN>

aws eks associate-access-policy \
  --cluster-name <CLUSTER> \
  --region <REGION> \
  --principal-arn <DEVOPS_AGENT_ROLE_ARN> \
  --policy-arn arn:aws:eks::aws:cluster-access-policy/AmazonAIOpsAssistantPolicy \
  --access-scope type=cluster
```

**If the access entry already exists** (e.g. created earlier via the EKS console, which
does not add Kubernetes groups), `create-access-entry` will fail with
`ResourceInUseException`. Add the group to the existing entry instead:

```bash
aws eks update-access-entry \
  --cluster-name <CLUSTER> \
  --region <REGION> \
  --kubernetes-groups eks-upgrade-check \
  --principal-arn <DEVOPS_AGENT_ROLE_ARN>
```

> **Note:** `update-access-entry --kubernetes-groups` **replaces** the entry's group
> list, it does not append. If the role's access entry already carries groups from other
> tooling, include them all in one comma-separated list, e.g.
> `--kubernetes-groups other-group,eks-upgrade-check`. Check the current groups first
> with the `describe-access-entry` command shown in Step 2's verification.

### Step 2: Grant assessment read permissions

Bind a least-privilege ClusterRole to the group from Step 1. This grants read-only
access to only the resources the assessment scans — no Secrets access — and the manifest
contains no IAM ARNs, so the same file works unchanged in every cluster.

```yaml
# eks-upgrade-check-rbac.yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: eks-upgrade-check
rules:
  # workload-risks: PDB coverage and drain-blocking PDB detection
  - apiGroups: ["policy"]
    resources: ["poddisruptionbudgets"]
    verbs: ["get", "list"]
  # deprecated-apis: live scan for removed/deprecated API usage
  - apiGroups: ["networking.k8s.io"]
    resources: ["networkpolicies", "ingresses"]
    verbs: ["get", "list"]
  - apiGroups: ["apiextensions.k8s.io"]
    resources: ["customresourcedefinitions"]
    verbs: ["get", "list"]
  - apiGroups: ["admissionregistration.k8s.io"]
    resources: ["validatingwebhookconfigurations", "mutatingwebhookconfigurations"]
    verbs: ["get", "list"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: eks-upgrade-check
subjects:
  - kind: Group
    name: eks-upgrade-check
    apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: ClusterRole
  name: eks-upgrade-check
  apiGroup: rbac.authorization.k8s.io
```

(Core workload reads — Deployments, DaemonSets, StatefulSets, Pods, Nodes, events, pod
logs — are already granted by `AmazonAIOpsAssistantPolicy` from Step 1; the ClusterRole
adds only what that policy does not cover.)

Unlike the AWS CLI commands above, `kubectl` does not take a cluster or region flag — it
applies to whatever cluster your current kubeconfig context points at. Point it at the
target cluster first:

```bash
aws eks update-kubeconfig --name <CLUSTER> --region <REGION>
kubectl apply -f eks-upgrade-check-rbac.yaml
```

**Verify both halves of the setup.** First confirm the access entry actually carries the
group — this is the step most often missed (the console access-entry flow does not add
groups), and without it the binding applies to nobody:

```bash
aws eks describe-access-entry \
  --cluster-name <CLUSTER> \
  --region <REGION> \
  --principal-arn <DEVOPS_AGENT_ROLE_ARN> \
  --query 'accessEntry.kubernetesGroups'
```

Expected output includes `"eks-upgrade-check"`. If it shows `[]` or the group is
missing, the ClusterRoleBinding applies to nobody. Fix it by adding the group, then
re-run the check above:

```bash
aws eks update-access-entry \
  --cluster-name <CLUSTER> \
  --region <REGION> \
  --kubernetes-groups eks-upgrade-check \
  --principal-arn <DEVOPS_AGENT_ROLE_ARN>
```

Then confirm the binding grants the reads (these test the RBAC objects only — they pass
regardless of the access entry, so always check the group above too):

```bash
kubectl auth can-i list poddisruptionbudgets --as-group eks-upgrade-check --as upgrade-check
kubectl auth can-i list customresourcedefinitions --as-group eks-upgrade-check --as upgrade-check -A
kubectl auth can-i list mutatingwebhookconfigurations --as-group eks-upgrade-check --as upgrade-check -A
```

All should print `yes`. The `-A` flag on cluster-scoped resources avoids a spurious
"not namespace scoped" warning.

### Step 3: Verify AWS API permissions

Steps 1–2 grant access to the Kubernetes API. The assessment also calls AWS APIs
directly (describing the cluster, node groups, add-ons, insights, and subnets). Agent
Space setup normally attaches the AWS-managed
[`AIDevOpsAgentAccessPolicy`](https://docs.aws.amazon.com/aws-managed-policy/latest/reference/AIDevOpsAgentAccessPolicy.html)
to the primary cloud source role, which already covers all of these — in that case there
is nothing to do. Confirm with:

```bash
aws iam list-attached-role-policies --role-name <AGENT_SPACE_ROLE_NAME>
```

(Use the bare role name, not the ARN.)

If your organization replaces the managed policy with a custom scoped one, it must allow:

- **EKS (read):** `ListClusters`, `DescribeCluster`, `ListNodegroups`, `DescribeNodegroup`, `ListAddons`, `DescribeAddon`, `DescribeAddonVersions`, `ListInsights`, `DescribeInsight`
- **EC2 (read):** `DescribeSubnets` (subnet IP capacity checks), `DescribeNetworkInterfaces` (unused-ENI remediation guidance)

Checks that hit a missing permission are marked with the denied action in the failure
reason — add that action to the custom policy and re-run.

### Rolling out at scale

For fleets of clusters, script Steps 1–2 with a per-cluster loop, or manage them via
Terraform (`aws_eks_access_entry`, `aws_eks_access_policy_association`, plus the RBAC
manifest) or GitOps (Argo CD / Flux syncing the ClusterRole and binding to every
cluster). Because the manifest is identical everywhere — no per-cluster ARNs — it can be
committed once and fanned out.

### Web search / web fetch capability

The Agent Space must also have **web search / web fetch enabled**. The skill verifies OSS
add-on compatibility live against upstream sources (the authoritative URLs in
`assets/oss_addon_registry.json`, plus fallback web searches). If the agent cannot reach
those sources — because web access is disabled — add-on version verification degrades to
`UNKNOWN_VERIFIABLE`: the add-on is identified but its compatibility with the target
Kubernetes version cannot be confirmed. Enable web access so add-on checks resolve to a
definitive verdict rather than an unverified one.

## Differences from the Claude Code version

The parent repo targets Claude Code; this port adapts the skill to the DevOps Agent's supported feature set:

| Claude Code (parent repo) | DevOps Agent (this folder) |
|---|---|
| Skill lives under `.claude/skills/eks-upgrade/` | Flat skill directory with `SKILL.md` at root |
| `steering/` for assessment logic | `references/` (same content, per Agent Skills spec) |
| `data/` and `tools/` directories | `assets/` for data files |
| `${CLAUDE_SKILL_DIR}/...` path variables | Relative paths (`references/`, `assets/`) |
| Local tool servers wired up per-project for cluster access and documentation lookup | Live cluster access and documentation/web lookup are provided at the Agent Space level |
| `md_to_html.py` script for HTML reports | Script execution not supported — the agent generates report artifacts directly (Markdown, or HTML inline) |
| Claude Code allowed-tools + `Bash`/`kubectl` | EKS / EC2 / Kubernetes read APIs available in the Agent Space |
| Tool names like `search_documentation`, `webFetch`, `get_eks_insights` | Generalized to capability descriptions (documentation search, web fetch, EKS Insights APIs) |

## Notes

- **No scripts.** Per DevOps Agent constraints, this port contains no executable scripts. The `md_to_html.py` converter from the parent repo is intentionally omitted; HTML output, if requested, is generated inline by the agent.
- **Compatibility is verified live.** `assets/oss_addon_registry.json` contains identifiers and authoritative upstream URLs only — never shipped compatibility data. The agent fetches live compatibility info from the referenced URLs.
- This is sample code for educational/demonstration purposes. Review and validate against your organization's security and operational requirements before use.
