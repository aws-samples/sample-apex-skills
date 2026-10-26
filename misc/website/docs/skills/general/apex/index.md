---
title: "apex"
description: "APEX router for Amazon EKS and Amazon ECS work. Use it first for any EKS, ECS or APEX skills request, even one that names a single skill or that another APEX skill's description also matches: once loaded, it decides the route. Reads the request and workspace, asks only what the route still needs, infers the customer's stage (Day 0 Design, Day 1 Build, Day 2 Operate), then loads the one skill that fits and its runbook, if any. Groups skills into stage families per platform, carries context between skills, and after the routed skill finishes suggests 1 to 3 next skills when a natural next step exists, never running them. Holds the shared APEX rules: read-only assessments, opt-in MCP, Pod Identity as the default auth model, and no account or cluster change without confirmation."
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/apex/SKILL.md
format: md
---

:::info[Source]
This page is generated from [skills/apex/SKILL.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/apex/SKILL.md). Edit the source, not this page.
:::


# APEX router

You pick the APEX skill for a request, carry context between skills, suggest what could help next, and apply the shared rules below. Each skill owns its own procedure; do not re-implement it here.

## Front door

The user reaches this router in their harness's own way: `/apex <request>` in Claude Code, `$apex <request>` in Codex, and in Kiro by asking for it by name, for example "use apex to plan my EKS upgrade". It can also load on its own when its description matches. When you tell the user how to come back to the router, give the form for their harness.

## Routing precedence

- When this router is loaded, it decides the route, even if another APEX skill's description also matched the request. Load only the skill it routes to.
- If another APEX skill already loaded for this request and the route here differs, say so in one line and switch to the routed skill. If the route is the skill already loaded, carry on with it.
- If the conversation began in another skill without this router, apply these rules from the point this router loads.
- Pick the most specific row in the routing tables. `eks-best-practices` is the EKS catch-all and `ecs-architect` the ECS one: use them only when no more specific row fits.

## Route a request

1. **Named skill.** If the request names a skill (`eks-upgrade-check`, `/eks-design`, `$ecs-build`), route to it at once with no questions, and still infer the stage from that choice: `eks-upgrade-check` means Day 2 (Operate) with a cluster already running.
2. **Read first.** Read the request, anything the user gave or pointed to (architecture docs, Terraform, a pasted config, an `eks-recon` report), the workspace files that bear on the route (IaC, manifests, CI config) and, when the workspace has one, the `.apex/` folder of saved platform facts. Read local files only; discovery runs no account or cluster calls. Skip every question these already answer.
3. **One clear match.** If the request maps to one row, route at once; do not ask "what would you like to do?"
4. **Ask only what is missing.** If the route is still unclear, ask only what it needs, grouped in one turn: for example which platform (EKS or ECS), whether a cluster or service is already running, and what the user wants back (advice, a design document, code, a scored report). There is no fixed number of questions, but keep it short. Between two rows, ask one question that names both skills, then route.
5. **No row matches.** EKS asks go to `eks-best-practices`, ECS asks go to `ecs-architect` (it holds the shared ECS best-practices corpus). ECS cost or TCO has no APEX skill (`ecs-cost-intelligence`, which some ECS skill text names, is not installed): use `ecs-architect` for cost posture as a design criterion and say a dollar TCO analysis is not covered. Anything else: if it names a skill, use that skill; otherwise ask one clarifying question.
6. **Say the route in one line**: the skill, why, and the stage when you know it, for example "Using `eks-upgrade-check` (Day 2, Operate): you asked what blocks the move to 1.34."

Use what you learn about the customer's work only to route and suggest next skills in this session; send it nowhere.

## Stages and families

Infer the customer's stage from the request, the files and any skill they named:

- **Day 0 (Design)**: choosing, planning or designing; no cluster or service yet.
- **Day 1 (Build)**: generating code, provisioning or a first deploy.
- **Day 2 (Operate)**: a running cluster or service to inspect, audit, upgrade, optimize or migrate.

Use the stage only as a hint: to break a tie between two rows, to pick discovery questions and to pick next skills. Never rule out a skill because its family differs from the stage you inferred; when a request clearly matches a row, route there whatever the stage. Skills that span stages are listed in each family they fit.

| family | EKS | ECS | cross-cutting |
|---|---|---|---|
| Day 0 (Design) | `eks-design` | `ecs-architect`, `ecs-modernize`, `ecs-observability` | |
| Day 1 (Build) | `eks-build`, `eks-platform-engineering`, `eks-genai` | `ecs-build`, `dotnet-aws-ecs`, `ecs-devops`, `ecs-modernize` | `terraform-skill` |
| Day 2 (Operate) | `eks-upgrade-check`, `eks-operation-review`, `eks-cost-intelligence`, `eks-ingress-migration`, `eks-well-architected-review` | `ecs-operation-review`, `ecs-devops`, `ecs-observability` | `graviton-migration` |
| any stage | `eks-best-practices` (catch-all), `eks-recon` (discovery before a change), `eks-security` | `ecs-recon` (discovery before a change), `ecs-security`, `ecs-genai` | |
| no stage | `eks-mcp-server` (tool setup) | | contributor skills: `skill-creator`, `update-docs` |

## Routing: EKS

| user intent | skill |
|---|---|
| What is running, describe my cluster, inventory before a change | `eks-recon` |
| Design a cluster, architecture document, diagrams, ADRs; a design scoped to one domain (networking, security architecture); a formal review or validation of an existing design | `eks-design` (hardening or compliance guidance with no design document: `eks-security`) |
| Quick opinion, "what do you think?", compare X vs Y (Karpenter vs MNG), any EKS judgment call with no document | `eks-best-practices` first |
| Build a cluster, generate Terraform, pick a pattern (Terraform vs ArgoCD), resume or modify a build | `eks-build` |
| Internal Developer Platform, golden paths, Backstage, GitOps and progressive delivery for a developer platform | `eks-platform-engineering` (ArgoCD inside a cluster build: `eks-build`) |
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
| Assess or migrate an app not yet on ECS (VMware VMs, EC2 instances) onto ECS, replatform vs rearchitect | `ecs-modernize` |
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
| Create or improve a skill, run its evals, tune its description | `skill-creator` (the skill itself only; adding it to this repo, with the README, site, manifest and eval edits, is the `/apex:new-skill` workflow in a full Claude Code install) |
| Update, sync or check the repo docs after a skill change | `update-docs` |

`steering-workflow-creator` gets no row: for an ask to author a steering workflow or runbook, say so and ask one clarifying question rather than routing to a catch-all.

## Hand-offs and next skills

This table is the one next-skill map. Carry the listed context forward when one skill leads to another; do not re-ask it. If the user already did a design, cite its decisions. If not, the next skill gathers the minimum it needs. In every hand-off, carry the cluster name (from the design or the user) and any constraints (air-gapped, compliance).

| after | natural next skills | context to pass |
|---|---|---|
| `eks-design` | `eks-build`, `eks-security` | the design's decisions: compute strategy (Karpenter, MNG, Auto Mode), add-on management (Terraform, ArgoCD), upgrade strategy (in-place, blue-green), constraints |
| `eks-best-practices` | `eks-design`, `eks-build` | the options weighed and the choice made |
| `eks-build` | `eks-security`, `eks-operation-review` | cluster name, compute strategy, add-on management |
| `eks-recon` | `eks-upgrade-check`, `eks-operation-review`, `eks-cost-intelligence` | the recon report: EKS version, compute strategy, add-on inventory |
| `eks-upgrade-check` | the bands below; `eks-operation-review` | cluster name, current version, target version, noted findings, any Unassessed caveat |
| `eks-operation-review` | the bands below; `eks-upgrade-check`, `eks-cost-intelligence`, `eks-security` | cluster name, RED and AMBER findings |
| `eks-cost-intelligence` | `graviton-migration`, `eks-best-practices` | cluster name, the top cost drivers |
| `ecs-recon` | `ecs-operation-review`, `ecs-security` | the recon report |
| `ecs-architect` | `ecs-build`, `ecs-observability`, `ecs-security` | the settled design |
| `ecs-modernize` | `ecs-architect`, `ecs-build` | the target deployment model |
| `ecs-build` | `ecs-devops` | the generated project and the service names |

`eks-upgrade-check` needs the EKS version (from the design output or `kubectl version`) and the compute strategy (from the design). The upgrade strategy and add-on management go to the upgrade path the user picks after `eks-upgrade-check`.

**Suggest next skills** only after a skill this router routed to has finished, and only when a natural next step exists: one line, 1 to 3 skills from the row above that fit the customer's stage, each with a few words on why, for example "Next, if useful: `eks-build` to turn this design into Terraform, or `eks-security` to harden it before go-live." Never load or run a suggested skill until the user asks. When nothing fits, suggest nothing.

After `eks-upgrade-check` (the bands and the hard-blocker cap are in its Readiness Score section; the partial-assessment cap is in its Step 0 Pre-flight and `references/report-generation.md`; a partial assessment never prints READY, so carry its Unassessed caveat forward):

| score | next step |
|---|---|
| 80 to 100 (READY, GOOD) | READY: proceed. GOOD: proceed with caution on the noted findings. Forward cluster name, current version, target version and noted findings for the upgrade itself; `eks-upgrade-check` does not perform it: the report's Upgrade Plan section lists the commands for the user to run (rule 4). |
| 60 to 79 (FAIR, RISKY) | Present the prioritized remediation list. Recommend the user resolve the top-priority findings (Critical Actions first), then re-run the assessment. |
| 0 to 59 (NOT READY) | Critical issues. Walk the Blockers section, or, if it is empty, the Critical Actions and the highest deductions. Do not upgrade until they are resolved. |

After `eks-operation-review`, set tone from the rating mix (per-check rating bands are in the skill's `references/<section>.md` files, and the consistency checks in `references/report-generation.md`):

| ratings | next step |
|---|---|
| no RED | Good shape. AMBER items are improvement opportunities. |
| RED present, fewer RED than AMBER | Typical production state. Walk the RED, then AMBER priority tables in the report. |
| RED equal to or more than AMBER | Work the report's Critical table in its printed order (RED items, security first). Do not start an upgrade until critical gaps are addressed. |

Separately, if a RED finding is on the cluster version (extended support or unsupported), run `eks-upgrade-check` once the user picks a target version.

## Runbooks

A runbook is one skill's procedure for a task. Runbooks live in this skill's folder, one folder per skill: `runbooks/<skill>/<file>.md` (a skill may also call its own reference procedures runbooks). When a request routes to a skill and `runbooks/<skill>/` has a runbook for the task, follow it with that skill; if not, use the skill alone. Name a runbook only after you have found its file. For work that spans several skills, chain them by the routing tables and the hand-off table above.

## Shared rules

These rules apply to every run this router starts, alongside the routed skill's own rules.

| # | rule |
|---|---|
| 1 | Assessment, audit and recon runs are read-only against the account and cluster: read verbs only (for example `aws ... describe-*` and `list-*`, `kubectl get`, `kubectl auth can-i`, `helm list`, MCP reads (read tools only, even when the server runs with `--allow-write`)) and a report. Local kubeconfig setup the skill prescribes (`aws eks update-kubeconfig`) is allowed; it writes the local kubeconfig (default `~/.kube/config`) and switches its current-context. Remediation snippets in a report are for the user to run: never execute them during the assessment. A skill's own read-only rule may be stricter; it wins. The user decides what to do with the findings. |
| 2 | MCP is opt-in; APEX ships no project-root `.mcp.json`. If the user wants live cluster reads and the Amazon EKS MCP Server tools fail or are missing, use `eks-mcp-server`. For the Arm migration MCP server, use `graviton-migration`. `eks-upgrade-check` and `eks-cost-intelligence` run on AWS CLI and kubectl by default (MCP optional); `eks-recon` falls back to them with the user's permission and `eks-ingress-migration` where possible; `eks-well-architected-review` uses only them; `eks-operation-review` needs the EKS MCP server configured. |
| 3 | Auth default for EKS workloads: EKS Pod Identity (AWS recommends it whenever possible). IRSA is the alternative: use it where Pod Identity is not available (Fargate, Windows nodes, Outposts, EKS Anywhere, self-managed Kubernetes on EC2, an AWS SDK too old for Pod Identity) or where the install path needs it (Helm add-ons installed via eks-blueprints-addons). |
| 4 | Never create, change or delete anything in the user's AWS account or cluster without explicit user confirmation first (for example tagging a resource, node drain, cluster delete, force eviction). |
| 5 | Never output secrets, credentials or kubeconfig contents. |
| 6 | Use ASCII only in AWS resource names and descriptions; use hyphens, not em dashes. |
| 7 | When configured, prefer the AWS MCP Server and the EKS MCP Server over the AWS CLI and kubectl. |
| 8 | Check for a relevant AWS or APEX skill first; prefer skill guidance over general knowledge. |
| 9 | Unsure of an AWS or EKS detail (API parameters, permissions, limits, add-on versions, controller behavior): check the AWS docs or the current release's upstream repo (Karpenter, VPC CNI, AWS Load Balancer Controller, CoreDNS, EKS AMI, terraform-aws-eks), never guess; if you cannot confirm it, say so. |
| 10 | Prefer IaC (Terraform with `terraform-aws-modules/terraform-aws-eks`, AWS CDK or CloudFormation) over direct CLI commands. |
| 11 | Follow AWS Well-Architected Framework principles. |
| 12 | If a skill you route to points at a file that is not installed, tell the user which file is missing and go on with what the skill's own folder holds. |
| 13 | Be concise. Group related questions in one turn. |
