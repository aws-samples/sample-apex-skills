# Router routing tables

The tables the router rules use (`router.most-specific-row`, `router.carry-context`, `router.suggest-never-run`). Pick the most specific row; the catch-all rows apply only when no more specific row fits.

## Stages and families

- **Day 0 (Design)**: choosing, planning or designing; no cluster or service yet.
- **Day 1 (Build)**: generating code, provisioning or a first deploy.
- **Day 2 (Operate)**: a running cluster or service to inspect, audit, upgrade, optimize or migrate.

Three ECS skills that span stages are listed in more than one family; others (`eks-genai`, `eks-platform-engineering`) sit in one family for now.

| family | EKS | ECS | cross-cutting |
|---|---|---|---|
| Day 0 (Design) | `eks-design` | `ecs-architect`, `ecs-modernize`, `ecs-observability` | |
| Day 1 (Build) | `eks-build`, `eks-platform-engineering`, `eks-genai` | `ecs-build`, `dotnet-aws-ecs`, `ecs-devops`, `ecs-modernize` | `terraform-skill` |
| Day 2 (Operate) | `eks-upgrade-check`, `eks-operation-review`, `eks-cost-intelligence`, `eks-ingress-migration`, `eks-well-architected-review` | `ecs-operation-review`, `ecs-devops`, `ecs-observability` | `graviton-migration` |
| any stage | `eks-best-practices` (catch-all), `eks-recon` (discovery before a change), `eks-security` | `ecs-recon` (discovery before a change), `ecs-security`, `ecs-genai` | |
| no stage | `eks-mcp-server` (tool setup) | | contributor skills: `skill-creator`, `update-docs` |

## No row matches

EKS asks go to `eks-best-practices`, ECS asks go to `ecs-architect` (it holds the shared ECS best-practices corpus). ECS cost or TCO has no APEX skill (`ecs-cost-intelligence`, which some ECS skill text names, is not installed): use `ecs-architect` for cost posture as a design criterion and say a dollar TCO analysis is not covered. A request outside EKS and ECS: say in one line that APEX covers EKS and ECS (plus the Terraform and contributor rows below), with no question first. A request whose platform cannot be told (not clearly EKS, ECS or outside both): ask one clarifying question, and if the answer still matches no row, say APEX has no skill for it.

## Routing: EKS

| user intent | skill |
|---|---|
| What is running, describe my cluster, inventory before a change | `eks-recon` |
| Design a cluster, architecture document, diagrams, ADRs; a design scoped to one domain (networking, security architecture); a formal review or validation of an existing design | `eks-design` (hardening or compliance guidance with no design document: `eks-security`) |
| Quick opinion, "what do you think?", compare X vs Y (Karpenter vs MNG), any EKS judgment call with no document | `eks-best-practices` first |
| Build a cluster, generate Terraform, pick a pattern (Terraform vs ArgoCD), resume or modify a build | `eks-build` |
| Internal Developer Platform, golden paths, Backstage, GitOps and progressive delivery for a developer platform | `eks-platform-engineering` (ArgoCD inside a cluster build: `eks-build`) |
| GenAI or LLM on EKS: GPU vs Neuron, vLLM, Ray, distributed training, RAG, AI gateway | `eks-genai` |
| Harden, compliance (HIPAA, PCI, FedRAMP, GDPR), CIS, Pod Identity vs IRSA, GuardDuty, image signing, PSA; CVE or advisory review ("am I exposed to CVE-...", check a security bulletin against my cluster); security event response (compromised image or package, leaked credential); security posture check (would my cluster contain a compromised pod) | `eks-security` |
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
| Should this run on ECS or EKS? | `ecs-architect` and `eks-best-practices` together, for a balanced comparison |
| Write, review or debug Terraform or OpenTofu modules, tests, CI, state, not tied to generating an EKS or ECS project | `terraform-skill` (questions about the `terraform-aws-modules/terraform-aws-eks` module: `eks-best-practices`) |

## Routing: contributor asks (about this repo, not a customer workload)

| user intent | skill |
|---|---|
| Create or improve a skill, run its evals, tune its description | `skill-creator`, then the new-skill steps in CONTRIBUTING.md (sibling map, triggering.json, catalogues) |
| Update, sync or check the repo docs after a skill change | `update-docs` |

An ask to author a runbook gets no row: say that a runbook is the customer's own procedure that chains skills, written by hand from the dummy examples in this skill's `runbooks/` folder (CONTRIBUTING.md, Creating a New Runbook), then ask one clarifying question rather than routing to a catch-all.

## Hand-offs and next skills

This table is the one next-skill map. In every hand-off, carry the cluster name (from the design or the user) and any constraints (air-gapped, compliance).

| after | natural next skills | context to pass |
|---|---|---|
| `eks-design` | `eks-build`, `eks-security` | the design's decisions: compute strategy (Karpenter, MNG, Auto Mode), add-on management (Terraform, ArgoCD), upgrade strategy (in-place, blue-green), constraints (air-gapped, compliance) |
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

After `eks-upgrade-check`, present its report with a one-paragraph summary of the blockers (if any) and the overall readiness rating, then take the band from the report; the score range of each band and the hard-blocker cap are in that skill's Readiness Score section, not here (the partial-assessment cap is in its Step 0 Pre-flight and `references/report-generation.md`; a partial assessment never prints READY, so carry its Unassessed caveat forward):

| band | next step |
|---|---|
| READY, GOOD | READY: proceed. GOOD: proceed with caution on the noted findings. Forward cluster name, current version, target version and noted findings for the upgrade itself; `eks-upgrade-check` does not perform it: the report's Upgrade Plan section lists the commands for the user to run (`apex.read-only-unless-confirmed`). |
| FAIR, RISKY | Present the prioritized remediation list. Recommend the user resolve the top-priority findings (Critical Actions first), then re-run the assessment. |
| NOT READY | Critical issues. Walk the Blockers section, or, if it is empty, the Critical Actions and the highest deductions. Do not upgrade until they are resolved. |

After `eks-operation-review`, set tone from the rating mix (per-check rating bands are in the skill's `references/<section>.md` files, and the consistency checks in `references/report-generation.md`):

| ratings | next step |
|---|---|
| no RED | Good shape. AMBER items are improvement opportunities. |
| RED present, fewer RED than AMBER | Typical production state. Walk the RED, then AMBER priority tables in the report. |
| RED present, equal to or more than AMBER | Work the report's Critical table in its printed order, then any RED Quick Wins (security first). Do not start an upgrade until critical gaps are addressed. |

Separately, if a RED finding is on the cluster version (extended support or unsupported), run `eks-upgrade-check` once the user picks a target version.
