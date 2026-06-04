# Evals — eks-design

## What these evals target

These inputs exercise the `eks-design` skill's declared scope: generating architecture design documents, Architecture Decision Records (ADRs), Mermaid diagrams, security architecture docs, and architecture validation/scoring reports for EKS deployments. `triggering.json` checks that the skill fires on prompts requesting design artifacts (documents, diagrams, ADRs, validation reports) and stays quiet for advisory questions, Terraform generation, cluster discovery, and code review prompts. `evals.json` checks the quality of two representative design tasks: full architecture document generation and architecture validation/scoring.

## Neighbour-skill disambiguation

The boundary between `eks-design` and its neighbours hinges on whether the prompt asks for a **design artifact** (document, diagram, ADR, validation report) versus a quick recommendation, executable code, cluster discovery, or engineering process guidance.

<!-- SIBLING_MAP_START -->
- **`eks-best-practices`** (advisory recommendations, tradeoff analysis, and quick architecture judgement calls without document generation) — negatives 11, 15, 18 ("Should I use Karpenter or MNG", "best practices for Karpenter consolidation", "quick recommendation, no doc needed").
- **`eks-build`** (generating Terraform modules, Helm charts, ArgoCD manifests, and executable IaC from a finalized design) — negatives 12, 17 ("Generate the Terraform modules", "Write the ArgoCD ApplicationSet and Kustomize overlays").
- **`terraform-skill`** (generic Terraform/OpenTofu code review and CI/CD unrelated to EKS architecture design) — negative 13 ("Review my Terraform PR for the EKS module").
- **`eks-recon`** (live cluster discovery, inventory, and pre-upgrade reconnaissance) — negatives 14, 16 ("What version of Kubernetes is my EKS cluster running", "inventory the node groups, namespaces, and IRSA roles").
- **`eks-operation-review`** (structured operational posture assessment with GREEN/AMBER/RED ratings) — negative 19 ("Run a structured operational review on my EKS cluster and produce a GREEN/AMBER/RED rated report").
- **`eks-platform-engineering`** (building an Internal Developer Platform / self-service on EKS) — negative 20 ("Help me build an Internal Developer Platform with Backstage portal, golden paths, and progressive delivery on EKS").
<!-- SIBLING_MAP_END -->

The key discriminator: `eks-design` fires when the prompt requests a **persistent design artifact** (architecture document, ADR, Mermaid diagram, validation report, or design-for-handoff-to-build) rather than a verbal recommendation, executable code, live cluster query, or process/standards check.

## Live-MCP caveat

Both `evals.json` tasks are self-contained — all required context is embedded in the prompt text (requirements for eval 1, existing architecture description for eval 2). Running these evals does **not** require a live EKS cluster or the EKS MCP server. Triggering evals (`triggering.json`) are matched against the skill's `description` frontmatter only and are never affected by MCP availability.

## How to run

From `misc/evals/`:
- `make validate-eks-design` — frontmatter + 64/1024-char limits (deterministic)
- `make triggering-eks-design` — triggering accuracy score (LIVE)
- `make task-eks-design` — task evals with grader (LIVE)
- `make process-eks-design` — process assertions against latest trajectory (deterministic)
- `make artifact-eks-design` — artifact validation against outputs/ (deterministic)
- `make composite-eks-design` — weighted composite score + letter grade (deterministic)
- `make snapshot-eks-design` — freeze current scores as baseline
- `make regression-eks-design` — compare against baseline, report delta

See `misc/evals/README.md` for the full capability catalogue (A–K) and `.skilleval.yaml` for weight configuration.
