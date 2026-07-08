# DevOps Agent Skills

This directory contains [AWS DevOps Agent](https://docs.aws.amazon.com/devopsagent/latest/userguide/) ports of selected APEX skills. These are non-executable markdown adaptations that run inside DevOps Agent's managed environment.

## What is AWS DevOps Agent?

AWS DevOps Agent is a managed AI service for release management and production operations. It investigates incidents, reviews releases, and handles operational queries across AWS, multicloud, and on-premises environments.

DevOps Agent consumes skills via the [Agent Skills specification](https://agentskills.io/) — specifically the **non-executable subset**: markdown instructions, data files, and reference documents. No scripts, no shell access.

## Which skills have DevOps Agent ports?

Only Day 2 operational skills that benefit from autonomous execution are ported:

### EKS

| Skill | Status | Source |
|-------|--------|--------|
| [eks-upgrade-check](eks-upgrade-check/) | Placeholder (vendored from upstream) | [sample-eks-upgrade-skill](https://github.com/aws-samples/sample-eks-upgrade-skill) |
| [eks-operation-review](eks-operation-review/) | Placeholder (vendored from upstream) | [sample-eks-operation-review-skill](https://github.com/aws-samples/sample-eks-operation-review-skill) |
| [eks-cost-intelligence](eks-cost-intelligence/) | Placeholder (authored in-place) | — |
| [eks-security](eks-security/) | Placeholder (authored in-place) | — |

## How to install into an Agent Space

### Option A — Import from repository (recommended)

1. In the Agent Space Operator Web App, go to **Knowledge → Skills → Add skill → Import from repository**.
2. Enter the GitHub directory URL pointing at the skill folder (e.g., `https://github.com/aws-samples/sample-apex-skills/tree/main/devops-agent/eks-upgrade-check`).
3. Select the agent type(s). **On-demand** is a good fit for user-invoked assessments.

### Option B — Upload as a zip

1. From **inside** the skill folder, zip its contents so `SKILL.md` sits at the zip root:

   ```bash
   cd devops-agent/eks-upgrade-check
   zip -r ../../eks-upgrade-check-skill.zip .
   ```

2. In the Operator Web App, go to **Knowledge → Skills → Add skill → Upload skill** and upload the zip (ZIP only, ≤ 6 MB).

## Differences from Claude Code skills

| Dimension | Claude Code (`skills/`) | DevOps Agent (`devops-agent/`) |
|-----------|------------------------|-------------------------------|
| Script execution | Full Bash, Python, kubectl | Not supported |
| MCP servers | Local `.mcp.json` config | Configured at Agent Space level |
| Tool access | `allowed-tools` frontmatter | Toolbox allowlist in Agent Space UI |
| Execution model | Interactive (can ask questions) | Fully autonomous (hard-stop or proceed) |
| Directory naming | `steering/`, `data/`, `tools/` | `references/`, `assets/` |
| Deployment | Symlinked via `npx apex-skills` | Zip upload or GitHub import |

## Key constraints

- **No scripts** — `scripts/` directory is rejected on upload
- **No `allowed-tools`** — tool access is configured at the Agent Space level
- **Fully autonomous** — skills must use hard-stop patterns instead of interactive prompts
- **Max 6 MB zip, 100 files** per skill
- **Read-only operations** — all skills in this directory are read-only by design

## Contributing

To add a DevOps Agent port for an existing skill:

1. Confirm the skill is Day 2 operational (upgrade checks, audits, assessments — not design or build workflows)
2. Create a subdirectory under `devops-agent/<skill-name>/`
3. Port the SKILL.md following the patterns in existing ports (see `eks-upgrade-check/` as reference)
4. Replace tool-specific names with capability descriptions
5. Add hard-stop decision tables for any interactive points
6. Validate: no scripts, no executable content, SKILL.md at root with valid frontmatter
