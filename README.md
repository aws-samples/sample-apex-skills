<div align="center">

<img src="misc/website/static/img/logo.svg" alt="APEX Skills" width="120">

# APEX Skills

**Platform engineering with agents: curated AWS skills for Amazon EKS and Amazon ECS, delivered through your AI coding agent.**

[![Docs](https://img.shields.io/badge/docs-GitHub%20Pages-blue)](https://aws-samples.github.io/sample-apex-skills/)
[![npm](https://img.shields.io/npm/v/apex-skills)](https://www.npmjs.com/package/apex-skills)
[![License: MIT-0](https://img.shields.io/badge/license-MIT--0-green)](LICENSE)
[![docs-sync](https://github.com/aws-samples/sample-apex-skills/actions/workflows/docs-sync.yml/badge.svg)](https://github.com/aws-samples/sample-apex-skills/actions/workflows/docs-sync.yml)

[Docs](https://aws-samples.github.io/sample-apex-skills/) · [Find a skill](https://aws-samples.github.io/sample-apex-skills/docs/skills/) · [Getting started](https://aws-samples.github.io/sample-apex-skills/docs/getting-started/) · [Contributing](CONTRIBUTING.md)

</div>

## What APEX is

- **Skills**: what your agent knows. 28 skills, written to the [Agent Skills standard](https://agentskills.io/), that design, build, review, upgrade and secure Amazon EKS and Amazon ECS estates.
- **The `/apex` router** (v2, from `main`): one entry point. Type `/apex` with your request and it picks the right skill and, when there is one, that skill's runbook.
- **DevOps Agent ports**: 6 Day 2 skills repackaged for [AWS DevOps Agent](https://docs.aws.amazon.com/devopsagent/latest/userguide/).

Domain knowledge by AWS Solutions Architects, TAMs and ProServe. 5 skills are vendored from upstream projects; see [Provenance](#provenance).

## Quick start

You need [Node.js 18+](https://nodejs.org/) and [git](https://git-scm.com/), on macOS or Linux (on Windows, use WSL).

```bash
npx apex-skills@1.3.0
```

The installer detects Claude Code and Kiro CLI, clones the repo to `~/.apex-skills/` and links the skills into place. It installs the latest v1 release of the skills.

Ask your agent in plain words and the matching skill loads:

> Is my EKS cluster ready to upgrade to 1.32?

In Claude Code the v1 install also adds `/apex:*` commands, such as `/apex:eks-upgrade-check`; Kiro CLI gets the same workflows as manual steering files in `~/.kiro/steering/`.

Flags, updates and uninstall: [installer README](misc/installer/README.md).

### The `/apex` router (v2, from `main`)

The router is new in v2, which is not released yet. To use it in Claude Code or Kiro CLI, install from `main` (this also moves an existing v1 install to `main`, which has no `/apex:*` commands):

```bash
npx apex-skills@1.3.0 --branch main
```

Then type your request after the router:

> /apex is my cluster ready to upgrade to 1.32?

For Codex, on a machine without the npx install, copy the skills by hand:

```bash
git clone https://github.com/aws-samples/sample-apex-skills.git
mkdir -p ~/.agents/skills && cp -r sample-apex-skills/skills/* ~/.agents/skills/
```

In Codex the router is `$apex`. `/apex` in Kiro CLI was tested on 2.35.1; 1.27.0 rejected it. Other harnesses, and the optional agent guardrails in [rules/AGENTS.md](rules/AGENTS.md): [Getting started](https://aws-samples.github.io/sample-apex-skills/docs/getting-started/).

## See it work

The [EKS Upgrade Readiness Check](examples/eks-upgrades/in-place-karpenter-check/) example, run in Claude Code:

| The agent finds your clusters | The scored result |
|---|---|
| ![Cluster discovery](examples/eks-upgrades/in-place-karpenter-check/static/cc/02-cluster-discovery.png) | ![Assessment result](examples/eks-upgrades/in-place-karpenter-check/static/cc/04-assessment-result.png) |

## How it fits

```mermaid
flowchart LR
  U[You] --> H[Agent harness<br/>Claude Code, Kiro CLI, Codex]
  H --> R["/apex router"]
  R --> S[Skill + runbook]
  S --> T["AWS CLI, kubectl or MCP servers,<br/>when the skill needs them"]
  T --> O[Report or code]
```

## Pick a skill by what you are doing

Not sure? Use [`/apex`](https://aws-samples.github.io/sample-apex-skills/docs/skills/general/apex/) (v2, from `main`) and it picks for you.

The tables describe `main`; v1.3.0 also ships steering-workflow-creator.

### Knowledge Skills

Guidance your agent draws on when you ask and decide.

| Skill | Use it to |
|---|---|
| [eks-best-practices](https://aws-samples.github.io/sample-apex-skills/docs/skills/eks/eks-best-practices/) | Answer EKS and Kubernetes architecture and configuration questions |
| [eks-genai](https://aws-samples.github.io/sample-apex-skills/docs/skills/eks/eks-genai/) | Plan GPU, Neuron, LLM serving or training on EKS |
| [eks-platform-engineering](https://aws-samples.github.io/sample-apex-skills/docs/skills/eks/eks-platform-engineering/) | Plan an internal developer platform on EKS |
| [ecs-genai](https://aws-samples.github.io/sample-apex-skills/docs/skills/ecs/ecs-genai/) | Run GPU, ML or LLM workloads on ECS |

### Day 0 Design

Choose an architecture before you build.

| Skill | Use it to |
|---|---|
| [eks-design](https://aws-samples.github.io/sample-apex-skills/docs/skills/eks/eks-design/) | Turn requirements into an EKS architecture you can review |
| [ecs-architect](https://aws-samples.github.io/sample-apex-skills/docs/skills/ecs/ecs-architect/) | Pick an ECS deployment model (Fargate, EC2, Managed Instances, Express Mode, Anywhere) |
| [ecs-observability](https://aws-samples.github.io/sample-apex-skills/docs/skills/ecs/ecs-observability/) | Choose how to log, measure and trace ECS services |

### Day 1 Build

Generate the infrastructure code and the release path.

| Skill | Use it to |
|---|---|
| [eks-build](https://aws-samples.github.io/sample-apex-skills/docs/skills/eks/eks-build/) | Generate a production-ready EKS cluster in Terraform |
| [ecs-build](https://aws-samples.github.io/sample-apex-skills/docs/skills/ecs/ecs-build/) | Generate apply-ready Terraform for ECS clusters and services |
| [ecs-devops](https://aws-samples.github.io/sample-apex-skills/docs/skills/ecs/ecs-devops/) | Set up safe deployments and CI/CD for ECS |
| [dotnet-aws-ecs](https://aws-samples.github.io/sample-apex-skills/docs/skills/general/dotnet-aws-ecs/) | Deploy a .NET app to ECS Fargate on Linux |
| [terraform-skill](https://aws-samples.github.io/sample-apex-skills/docs/skills/general/terraform-skill/) | Write, review or debug Terraform and OpenTofu |

### Day 2 Operate: assess what is running

Discover, score and review a live cluster or estate.

| Skill | Use it to |
|---|---|
| [eks-recon](https://aws-samples.github.io/sample-apex-skills/docs/skills/eks/eks-recon/) | Find out what an EKS cluster is running |
| [ecs-recon](https://aws-samples.github.io/sample-apex-skills/docs/skills/ecs/ecs-recon/) | Find out what an ECS environment is running |
| [eks-operation-review](https://aws-samples.github.io/sample-apex-skills/docs/skills/eks/eks-operation-review/) | Audit the operational health of a live EKS cluster |
| [ecs-operation-review](https://aws-samples.github.io/sample-apex-skills/docs/skills/ecs/ecs-operation-review/) | Audit the operational health of a live ECS estate |
| [eks-well-architected-review](https://aws-samples.github.io/sample-apex-skills/docs/skills/eks/eks-well-architected-review/) | Run an unofficial Well-Architected-style review of an EKS cluster (not the AWS Well-Architected Tool) (Linux nodes only) |
| [eks-cost-intelligence](https://aws-samples.github.io/sample-apex-skills/docs/skills/eks/eks-cost-intelligence/) | Find where an EKS cluster wastes money |

### Day 2 Operate: upgrade and migrate

Move a version, a controller, a CPU architecture or an app.

| Skill | Use it to |
|---|---|
| [eks-upgrade-check](https://aws-samples.github.io/sample-apex-skills/docs/skills/eks/eks-upgrade-check/) | Check if an EKS cluster is ready for its next Kubernetes version |
| [eks-ingress-migration](https://aws-samples.github.io/sample-apex-skills/docs/skills/eks/eks-ingress-migration/) | Plan the move off NGINX Ingress on EKS |
| [graviton-migration](https://aws-samples.github.io/sample-apex-skills/docs/skills/general/graviton-migration/) | Move workloads from x86 to Graviton (arm64) |
| [ecs-modernize](https://aws-samples.github.io/sample-apex-skills/docs/skills/ecs/ecs-modernize/) | Move an existing VMware or EC2 app onto ECS |

### Day 2 Operate: secure

Check exposure, harden and prepare for audits.

| Skill | Use it to |
|---|---|
| [eks-security](https://aws-samples.github.io/sample-apex-skills/docs/skills/eks/eks-security/) | Check an EKS cluster for exposure, respond to a security event and harden it (the exposure check and event response are v2, from `main`) |
| [ecs-security](https://aws-samples.github.io/sample-apex-skills/docs/skills/ecs/ecs-security/) | Harden ECS tasks, roles, secrets and images |

### Set up and extend

Connect tools, write your own skills, keep docs in sync.

| Skill | Use it to |
|---|---|
| [apex](https://aws-samples.github.io/sample-apex-skills/docs/skills/general/apex/) | Describe the task and apex picks the skill (v2, from `main`) |
| [eks-mcp-server](https://aws-samples.github.io/sample-apex-skills/docs/skills/eks/eks-mcp-server/) | Connect your agent to the EKS MCP Server |
| [skill-creator](https://aws-samples.github.io/sample-apex-skills/docs/skills/general/skill-creator/) | Write a new skill or improve an existing one |
| [update-docs](https://aws-samples.github.io/sample-apex-skills/docs/skills/general/update-docs/) | Bring every APEX docs surface in line after a skill change |

<!-- SKILLS_REFERENCE_START -->
## Skills Reference

> _This table is auto-generated by [`misc/update-skills-references.sh`](misc/update-skills-references.sh). Do not edit manually._

### EKS Skills

<table>
<tr><td><a href="https://aws-samples.github.io/sample-apex-skills/docs/skills/eks/eks-best-practices/"><b>eks-best-practices</b></a></td><td><a href="https://aws-samples.github.io/sample-apex-skills/docs/skills/eks/eks-build/"><b>eks-build</b></a></td><td><a href="https://aws-samples.github.io/sample-apex-skills/docs/skills/eks/eks-cost-intelligence/"><b>eks-cost-intelligence</b></a></td><td><a href="https://aws-samples.github.io/sample-apex-skills/docs/skills/eks/eks-design/"><b>eks-design</b></a></td></tr>
<tr><td><a href="https://aws-samples.github.io/sample-apex-skills/docs/skills/eks/eks-genai/"><b>eks-genai</b></a></td><td><a href="https://aws-samples.github.io/sample-apex-skills/docs/skills/eks/eks-ingress-migration/"><b>eks-ingress-migration</b></a></td><td><a href="https://aws-samples.github.io/sample-apex-skills/docs/skills/eks/eks-mcp-server/"><b>eks-mcp-server</b></a></td><td><a href="https://aws-samples.github.io/sample-apex-skills/docs/skills/eks/eks-operation-review/"><b>eks-operation-review</b></a></td></tr>
<tr><td><a href="https://aws-samples.github.io/sample-apex-skills/docs/skills/eks/eks-platform-engineering/"><b>eks-platform-engineering</b></a></td><td><a href="https://aws-samples.github.io/sample-apex-skills/docs/skills/eks/eks-recon/"><b>eks-recon</b></a></td><td><a href="https://aws-samples.github.io/sample-apex-skills/docs/skills/eks/eks-security/"><b>eks-security</b></a></td><td><a href="https://aws-samples.github.io/sample-apex-skills/docs/skills/eks/eks-upgrade-check/"><b>eks-upgrade-check</b></a></td></tr>
<tr><td><a href="https://aws-samples.github.io/sample-apex-skills/docs/skills/eks/eks-well-architected-review/"><b>eks-well-architected-review</b></a></td><td></td><td></td><td></td></tr>
</table>

### ECS Skills

<table>
<tr><td><a href="https://aws-samples.github.io/sample-apex-skills/docs/skills/ecs/ecs-architect/"><b>ecs-architect</b></a></td><td><a href="https://aws-samples.github.io/sample-apex-skills/docs/skills/ecs/ecs-build/"><b>ecs-build</b></a></td><td><a href="https://aws-samples.github.io/sample-apex-skills/docs/skills/ecs/ecs-devops/"><b>ecs-devops</b></a></td></tr>
<tr><td><a href="https://aws-samples.github.io/sample-apex-skills/docs/skills/ecs/ecs-genai/"><b>ecs-genai</b></a></td><td><a href="https://aws-samples.github.io/sample-apex-skills/docs/skills/ecs/ecs-modernize/"><b>ecs-modernize</b></a></td><td><a href="https://aws-samples.github.io/sample-apex-skills/docs/skills/ecs/ecs-observability/"><b>ecs-observability</b></a></td></tr>
<tr><td><a href="https://aws-samples.github.io/sample-apex-skills/docs/skills/ecs/ecs-operation-review/"><b>ecs-operation-review</b></a></td><td><a href="https://aws-samples.github.io/sample-apex-skills/docs/skills/ecs/ecs-recon/"><b>ecs-recon</b></a></td><td><a href="https://aws-samples.github.io/sample-apex-skills/docs/skills/ecs/ecs-security/"><b>ecs-security</b></a></td></tr>
</table>

### General

<table>
<tr><td><a href="https://aws-samples.github.io/sample-apex-skills/docs/skills/general/apex/"><b>apex</b></a></td><td><a href="https://aws-samples.github.io/sample-apex-skills/docs/skills/general/dotnet-aws-ecs/"><b>dotnet-aws-ecs</b></a></td><td><a href="https://aws-samples.github.io/sample-apex-skills/docs/skills/general/graviton-migration/"><b>graviton-migration</b></a></td></tr>
<tr><td><a href="https://aws-samples.github.io/sample-apex-skills/docs/skills/general/skill-creator/"><b>skill-creator</b></a></td><td><a href="https://aws-samples.github.io/sample-apex-skills/docs/skills/general/terraform-skill/"><b>terraform-skill</b></a></td><td><a href="https://aws-samples.github.io/sample-apex-skills/docs/skills/general/update-docs/"><b>update-docs</b></a></td></tr>
</table>
<!-- SKILLS_REFERENCE_END -->

<!-- EXAMPLES_REFERENCE_START -->
## Examples

> _This table is auto-generated by [`misc/update-examples-references.sh`](misc/update-examples-references.sh). Do not edit manually._

| Example | Description | Workflow |
|---------|-------------|----------|
| **[Liberty to ECS Modernization](examples/ecs-modernize/liberty-to-ecs/)** | Assess a Java 8 / WebSphere Liberty application carrying planted modernization blockers, score it with the APEX ecs-modernize skill, then execute both migration paths on ECS — Replatform as-is onto ECS on EC2 and Rearchitect onto Fargate — and re-assess to see the Fit_Score rise from the Replatform band into the Rearchitect band. | -- |
| **[EKS Upgrade Readiness Check](examples/eks-upgrades/in-place-karpenter-check/)** | Deploy an EKS 1.32 cluster with Karpenter v1.0.2 and planted upgrade issues, then run the APEX EKS upgrade-check skill to produce a scored readiness report showing NOT READY status. | [eks-upgrade-check](skills/apex/runbooks/eks-upgrade-check/eks-upgrade-check.md) |
<!-- EXAMPLES_REFERENCE_END -->

## DevOps Agent

6 Day 2 skills (eks-cost-intelligence, eks-ingress-migration, eks-operation-review, eks-recon, eks-security, eks-upgrade-check) are ported for managed autonomous runs in AWS DevOps Agent: see [devops-agent/](devops-agent/README.md).

## Provenance

5 skills are vendored from upstream and synced by `misc/sync-*.sh`; do not edit them here. Three carry small sync-time edits, listed in each skill's UPSTREAM.md.

| Skill | Upstream | License |
|---|---|---|
| skill-creator | [anthropics/skills](https://github.com/anthropics/skills) | Apache 2.0 |
| terraform-skill | [antonbabenko/terraform-skill](https://github.com/antonbabenko/terraform-skill) | Apache 2.0 |
| dotnet-aws-ecs | [adisimon217/sample-appmod-skills](https://github.com/adisimon217/sample-appmod-skills) | MIT |
| eks-operation-review | [aws-samples/sample-eks-operation-review-skill](https://github.com/aws-samples/sample-eks-operation-review-skill) | MIT-0 |
| eks-upgrade-check | [aws-samples/sample-eks-upgrade-skill](https://github.com/aws-samples/sample-eks-upgrade-skill) | MIT-0 |

Details: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and the UPSTREAM.md of [dotnet-aws-ecs](skills/dotnet-aws-ecs/UPSTREAM.md), [eks-operation-review](skills/eks-operation-review/UPSTREAM.md) and [eks-upgrade-check](skills/eks-upgrade-check/UPSTREAM.md).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for adding skills, runbooks and examples. Security issues: [CONTRIBUTING.md, Security Issue Notifications](CONTRIBUTING.md#security-issue-notifications).

## Disclaimer

Sample code for **educational and demonstration purposes only**. It is not intended for direct production use without proper review, testing, and validation. Test generated infrastructure (Terraform, Helm charts, kubectl commands) in non-production environments first. Use at your own risk: the authors are not responsible for any issues, damages, or losses that may result from using this code in production.

## License

MIT-0. See [LICENSE](LICENSE).
