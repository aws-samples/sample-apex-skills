# Evals — eks-build

## What these evals target

These evals exercise the code-generation slice of eks-build: scaffolding complete EKS Terraform projects, configuring addons with IRSA/Pod Identity, and producing ArgoCD manifests for GitOps-managed clusters. `triggering.json` validates that prompts requesting infrastructure generation route here (not to design, recon, or generic Terraform skills), while `evals.json` checks that generated output is structurally complete and production-ready.

## Neighbour-skill disambiguation

eks-build focuses on producing deployable infrastructure code; neighbouring skills handle architecture decisions, operational guidance, generic IaC, engineering standards, and cluster discovery.

<!-- SIBLING_MAP_START -->
- **`eks-design`** (architecture design documents, ADRs, and system diagrams for EKS solutions) — negatives 11, 12 ("Design an EKS architecture that balances cost…", "Write an Architecture Decision Record for choosing Fargate vs managed node groups").
- **`eks-best-practices`** (operational recommendations, upgrade strategies, and security posture guidance for running EKS clusters) — negatives 13, 17 ("best practices for EKS cluster upgrades and version skew", "security group rules for pod-to-pod communication").
- **`terraform-skill`** (generic Terraform/OpenTofu module development, testing frameworks, and CI/CD pipelines unrelated to EKS) — negatives 14, 15, 18 ("generic Terraform module for an S3 bucket", "Review my Terraform code for style issues", "Terratest integration test for my generic VPC module").
- **`eks-recon`** (discovering existing EKS clusters, enumerating addons, and auditing live cluster state) — negative 16 ("Discover all EKS clusters in my AWS account").
- **`eks-operation-review`** (structured operational posture assessment with GREEN/AMBER/RED ratings) — negative 19 ("Audit my EKS cluster's operational posture across networking, RBAC, observability, and workload config").
- **`eks-platform-engineering`** (building an Internal Developer Platform / self-service on EKS) — negative 20 ("Set up an Internal Developer Platform with Backstage, Keycloak SSO, and DORA metrics on our EKS cluster").
<!-- SIBLING_MAP_END -->

The key discriminator is intent to generate deployable EKS infrastructure code. If the prompt asks to produce Terraform, Helm values, or ArgoCD manifests specifically for building an EKS cluster or its addons, it belongs here. If it asks about architecture choices, operational advice, non-EKS IaC, engineering process, or cluster discovery, it routes elsewhere.

## Live-MCP caveat

These evals do not require a live EKS cluster or MCP server. All prompts carry sufficient context (region, version, addon list, constraints) to be answered from the skill's embedded knowledge and templates alone. Running these evals requires no MCP availability.

## How to run

From `misc/evals/`:
- `make validate-eks-build` — frontmatter + 64/1024-char limits (deterministic)
- `make triggering-eks-build` — triggering accuracy score (LIVE)
- `make task-eks-build` — task evals with grader (LIVE)
- `make process-eks-build` — process assertions against latest trajectory (deterministic)
- `make artifact-eks-build` — artifact validation against outputs/ (deterministic)
- `make composite-eks-build` — weighted composite score + letter grade (deterministic)
- `make snapshot-eks-build` — freeze current scores as baseline
- `make regression-eks-build` — compare against baseline, report delta

See `misc/evals/README.md` for the full capability catalogue (A–K) and `.skilleval.yaml` for weight configuration.
