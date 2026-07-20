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

See [`SKILL.md`](../SKILL.md) for the full assessment workflow.

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

This skill requires your AWS DevOps Agent (Agent Space) to have access to the EKS
cluster(s) you want to assess. Follow the official AWS guide to grant it:
[AWS EKS access setup](https://docs.aws.amazon.com/devopsagent/latest/userguide/configuring-integrations-and-knowledge-aws-eks-access-setup.html).
An access entry must be created for each cluster you want the agent to assess.

The Agent Space role also needs read access to the supporting AWS APIs the skill uses:

- **EKS (read):** `DescribeCluster`, `ListClusters`, `ListNodegroups`, `DescribeNodegroup`, `ListAddons`, `DescribeAddon`, `DescribeAddonVersions`, `ListInsights`, `DescribeInsight`
- **EC2 (read):** `DescribeSubnets`

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
