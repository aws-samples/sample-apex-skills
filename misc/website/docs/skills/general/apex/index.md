---
title: "apex"
description: "APEX router and shared rules. Use when a request is about Amazon EKS, Amazon ECS or the APEX skills in general and does not clearly name one skill, spans several skills (for example design, then build, then upgrade), or asks which APEX skill to use. Picks the right skill by name from a routing table grouped EKS, ECS, cross-cutting and contributor, carries context between skills, and holds shared rules for APEX work: read the user's context first, route early, read-only assessments, opt-in MCP, Pod Identity as the default auth model, no destructive action without confirmation. Skip when the request already matches one skill's own description: use that skill directly."
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/apex/SKILL.md
format: md
---

:::info[Source]
This page is generated from [skills/apex/SKILL.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/apex/SKILL.md). Edit the source, not this page.
:::


# APEX router

Reader: an agent. This skill is the APEX router: it picks the APEX skill for a request and holds the shared APEX rules. It works when only the skills folder is copied: it needs no other file. Route by skill name. Each skill owns its own procedure; do not re-implement it here. One exception until it moves into the skill: `eks-operation-review` still reads its workflow from `~/.claude/apex-steering/workflows/eks-operation-review.md`, which a skills-only copy does not have.

## Shared rules

| # | rule |
|---|---|
| 1 | Detect intent early. If the first message maps to one skill, route at once; do not ask "what would you like to do?" |
| 2 | Explain routing in one line: say which skill you are using and why. |
| 3 | Ambiguous between two skills: ask one question that names both, then route. |
| 4 | No row matches: EKS asks go to `eks-best-practices`, ECS asks go to `ecs-architect` (it holds the shared ECS best-practices corpus). ECS cost or TCO has no APEX skill yet (`ecs-cost-intelligence`, named in ECS skill descriptions, does not exist): use `ecs-architect` for cost posture as a design criterion and say a dollar TCO analysis is not covered. Anything else: if it names a skill, use that skill; otherwise ask one clarifying question. |
| 5 | Read first. If the user gives architecture docs, Terraform, a pasted config or an `eks-recon` report, read it and skip questions it already answers. |
| 6 | Be concise. Group related questions in one turn. |
| 7 | Assessment, audit and recon runs are read-only against the account and cluster: read verbs only (for example `aws ... describe-*` and `list-*`, `kubectl get`, `kubectl auth can-i`, `helm list`, MCP reads) and a report. Local kubeconfig setup the skill prescribes (`aws eks update-kubeconfig`) is allowed. Remediation snippets in a report are for the user to run: never execute them. A skill's own read-only rule may be stricter; it wins. The user decides what to do with the findings. |
| 8 | MCP is opt-in; APEX ships no project-root `.mcp.json`. If the user wants live cluster reads and the EKS MCP tools fail or are missing, use `eks-mcp-server`. For the Arm migration MCP server, use `graviton-migration`. `eks-upgrade-check` falls back to AWS CLI and kubectl; `eks-operation-review` needs the EKS MCP server configured. |
| 9 | Auth default for EKS workloads: EKS Pod Identity (recommended for new workloads). IRSA is a fully supported alternative: use it where Pod Identity is not available (Fargate, Windows nodes, Outposts, EKS Anywhere, self-managed Kubernetes on EC2) or where the install path needs it (Helm add-ons installed via eks-blueprints-addons). |
| 10 | Never run destructive operations (node drain, cluster delete, force eviction) without explicit user confirmation. |
| 11 | Never output secrets, credentials or kubeconfig contents. |
| 12 | Use ASCII only in AWS resource names and descriptions; use hyphens, not em dashes. |

## Routing: EKS

| user intent | skill |
|---|---|
| What is running, describe my cluster, inventory before a change | `eks-recon` |
| Design a cluster, architecture document, diagrams, ADRs; a design scoped to one domain (networking, security architecture); a formal review or validation of an existing design | `eks-design` (hardening or compliance guidance with no design document: `eks-security`) |
| Quick opinion, "what do you think?", compare X vs Y (Karpenter vs MNG), any EKS judgment call with no document | `eks-best-practices` |
| Build a cluster, generate Terraform, pick a pattern (Terraform vs ArgoCD), resume or modify a build | `eks-build` |
| Internal Developer Platform, golden paths, Backstage, GitOps and progressive delivery | `eks-platform-engineering` |
| GenAI or LLM on EKS: GPU vs Neuron, vLLM, Ray, distributed training, RAG, AI gateway | `eks-genai` |
| Harden, compliance (HIPAA, PCI, FedRAMP, GDPR), CIS, Pod Identity vs IRSA, GuardDuty, image signing, PSA | `eks-security` |
| Ready to upgrade to a target version, what blocks my upgrade | `eks-upgrade-check` |
| Operational review, audit, health check, score my posture, one section (networking, RBAC, observability), version currency with no target version | `eks-operation-review` |
| Cost audit, waste, biggest cost driver, Spot or Graviton savings | `eks-cost-intelligence` |
| Move off NGINX ingress, Gateway API or ALB migration assessment | `eks-ingress-migration` (general ingress advice: `eks-best-practices`) |
| Well-Architected review, only when the user names the Framework or WAFR | `eks-well-architected-review` (a generic audit or score goes to `eks-operation-review`) |
| EKS MCP server install, config or tools not showing | `eks-mcp-server` |

## Routing: ECS

| user intent | skill |
|---|---|
| What is running in my ECS environment, describe a service or task definition | `ecs-recon` |
| Choose and design an ECS deployment model for a new workload: Fargate, EC2, Managed Instances, Express Mode, ECS Anywhere | `ecs-architect` |
| Generate ECS Terraform for a settled design | `ecs-build` |
| Deploy, release, blue/green or canary, CI/CD, stuck deployment | `ecs-devops` |
| GPU, ML or GenAI on ECS | `ecs-genai` |
| Assess or migrate an existing app (VMware, EC2) onto ECS, replatform vs rearchitect | `ecs-modernize` |
| Deploy a .NET app to ECS Fargate on Linux with CloudFormation or CDK | `dotnet-aws-ecs` |
| Logs, metrics, tracing, alerting design for ECS | `ecs-observability` |
| Audit, health check or GREEN/AMBER/RED score of a live ECS estate | `ecs-operation-review` |
| Task role vs execution role, secrets injection, hardening, compliance on ECS | `ecs-security` ("audit my ECS security posture" matches both this and `ecs-operation-review`: ask) |

## Routing: cross-cutting

| user intent | skill |
|---|---|
| Migrate workloads from x86 to Graviton (arm64): readiness scan, node cutover, multi-arch builds | `graviton-migration` (savings estimate: `eks-cost-intelligence`; "should I use Graviton?": `eks-best-practices`) |
| Write, review or debug Terraform or OpenTofu modules, tests, CI, state, not tied to generating an EKS or ECS project | `terraform-skill` |

## Routing: contributor asks (about this repo, not a customer workload)

| user intent | skill |
|---|---|
| Create or improve a skill, run its evals, tune its description | `skill-creator` |
| Update, sync or check the repo docs after a skill change | `update-docs` |

## Hand-offs between skills

Carry known context forward when one skill leads to another; do not re-ask it.

| context | comes from | needed by |
|---|---|---|
| cluster name | design or the user | every skill that targets a cluster |
| EKS version | design output or `kubectl version` | `eks-upgrade-check` |
| compute strategy (Karpenter, MNG, Auto Mode) | design | `eks-upgrade-check` |
| upgrade strategy (in-place, blue-green) | design | `eks-upgrade-check` |
| add-on management (Terraform, ArgoCD) | design | `eks-upgrade-check` |
| constraints (air-gapped, compliance) | design | every skill |

If the user already did a design, cite its decisions. If not, the next skill gathers the minimum it needs.

After `eks-upgrade-check` (the bands, the hard-blocker cap and the partial-assessment cap are the skill's own, in its Readiness Score section; a partial assessment never prints READY, so carry its Unassessed caveat forward):

| score | next step |
|---|---|
| 80 to 100 (READY, GOOD) | Ready to proceed. Forward cluster name, current version, target version and noted findings to whatever upgrade path the user picks. |
| 60 to 79 (FAIR, RISKY) | Present the prioritized remediation list. Recommend the user resolve the top blockers, then re-run the assessment. |
| 0 to 59 (NOT READY) | Hard blockers. Walk the blocker section. Do not upgrade until they are fixed. |

After `eks-operation-review`, set tone from the rating mix (rating rules and the consistency contract are the skill's own):

| ratings | next step |
|---|---|
| mostly GREEN, no RED | Good shape. AMBER items are improvement opportunities. |
| several AMBER, some RED | Typical production state. Walk the RED, then AMBER priority tables in the report. |
| many RED | Recommend the user address security-flagged RED first. Do not start an upgrade until critical gaps are addressed. |
| RED "version on extended support" | Once the user picks a target version, run `eks-upgrade-check`. |

## Runbooks

A runbook is a skill's guided procedure (questionnaire, checkpoints, report). When a skill has one, it sits in that skill's own folder as `runbook/<file>.md`, and the skill's SKILL.md says when to follow it. Route to the skill, not to the runbook. For work that spans several skills, chain them by the routing tables and hand-offs above.
