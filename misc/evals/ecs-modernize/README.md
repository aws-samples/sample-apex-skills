# Evals — ecs-modernize

## What these evals target

These evals exercise ecs-modernize's two-phase pipeline: the read-only modernization assessment (tech-stack detection, blocker detection, Fit_Score, Replatform-vs-Rearchitect recommendation, Modernization_Report) and the gated migration execution (Execution_Gate, per-action-class confirmations, Transformation_Plan with optional AWS Transform augmentation, Windows container path, deploy verification). `triggering.json` checks description-fit only — that existing-app-to-ECS migration prompts fire and that greenfield ECS design or Kubernetes/EKS migration prompts do not. `evals.json` checks task behaviour: scoring discipline, blocker handling, degraded-input handling, gate enforcement, delegation boundaries, and execution safety rails.

## Neighbour-skill disambiguation

The boundary is about **where the work starts and what it targets**: this skill starts from an *existing application's source code* and drives it onto *ECS*. Neighbours own greenfield design depth, Linux-path IaC generation, live-estate discovery, security hardening, and anything Kubernetes-shaped.

<!-- SIBLING_MAP_START -->
- **`ecs-architect`** (Day-0 ECS deployment-model selection and detailed target design — launch types, capacity-provider strategy, task sizing, networking for new workloads) — negatives 11, 12, 13, 14 ("brand-new containerized API from scratch — which ECS launch type", "greenfield service we haven't written yet", "Day-0 design, nothing exists yet", "new project kickoff … greenfield microservice").
- **`ecs-build`** (apply-ready Terraform generation for Linux container paths on ECS — clusters, services, task definitions) — negative 19 ("Our .NET 8 API is already cloud-ready and containerized — just generate the Fargate Terraform/CDK to deploy it … no assessment needed"); the handoff boundary is also exercised inside `evals.json` (ids 11, 17), where the skill must delegate Linux-path Terraform instead of generating it.
- **`ecs-recon`** (read-only discovery and inventory of a live ECS estate) — no dedicated near-miss prompt; the boundary is exercised in `evals.json` (id 11), where a live-cluster inventory request must be delegated without calling enumeration APIs.
- **`ecs-security`** (ECS security and compliance hardening — IAM design, secrets management, compliance audits) — no dedicated near-miss prompt; the boundary is exercised in `evals.json` (id 11), where a hardening request must be delegated rather than designed here.
- **`eks-design`** (EKS architecture design; the entry point for Kubernetes-targeted migrations) — negatives 15, 16, 17, 18 ("Migrate our application to Kubernetes on Amazon EKS", "move our on-prem workloads to EKS", "Design an EKS architecture", "we've standardized on EKS, ECS is not an option").
<!-- SIBLING_MAP_END -->

The discriminator: if the user has an *existing app* (EC2/VMware) and wants it *assessed for or migrated onto ECS* — containerization readiness, replatform-vs-rearchitect, fit scoring, or executing an approved migration — it is this skill. If nothing exists yet and they want the deployment model designed (`ecs-architect`), if they only want Linux-path ECS Terraform generated (`ecs-build`), an inventory of what is already running (`ecs-recon`), a hardening design (`ecs-security`), or the target is Kubernetes/EKS (`eks-design`), it is not.

## Live-MCP caveat

These evals require no live cluster, no MCP server, and no AWS credentials. The `triggering.json` prompts are description-fit only. The `evals.json` prompts carry their full context inline: assessment prompts include a synthetic source-tree inventory in the prompt text (the `./fixtures/...` paths are narrative, not real fixture files), and execution-phase prompts state prior approvals and supply **mocked AWS responses** inline where read-only API results are needed (e.g. id 20 embeds simulated DescribeServices/DescribeTasks output for deploy verification). A run is graded on whether the skill honours its read-only invariants, gates, and delegation rules against that stated context — by default nothing should touch a real AWS account.

## How to run

From `misc/evals/`:
- `make validate-ecs-modernize` — frontmatter + 64/1024-char limits (deterministic)
- `make triggering-ecs-modernize` — triggering accuracy score (LIVE)
- `make task-ecs-modernize` — task evals with grader (LIVE)
- `make process-ecs-modernize` — process assertions against latest trajectory (deterministic)
- `make artifact-ecs-modernize` — artifact validation against outputs/ (deterministic)
- `make composite-ecs-modernize` — weighted composite score + letter grade (deterministic)

See `misc/evals/README.md` for the full capability catalogue (A–K) and `.skilleval.yaml` for weight configuration. Note: layers 1–3 (process/artifact/knowledge) are disabled in `.skilleval.yaml` until assertion fields are added to `evals.json`.
