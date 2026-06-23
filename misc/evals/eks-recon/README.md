# `eks-recon` evals

## What these evals target

These artifacts exercise the `eks-recon` skill, whose job is read-only discovery of an existing EKS cluster: current version, compute strategy (Karpenter / MNG / Auto Mode / Fargate), IaC tooling, CI/CD pipelines, add-on inventory, networking, security posture, and observability. `triggering.json` checks that the skill fires on realistic recon phrasings and does NOT fire on near-miss requests that belong to its sibling skills. `evals.json` sketches two end-to-end recon tasks (upgrade-prep context and a team handoff) that a good recon response must cover.

## Neighbour-skill disambiguation

<!-- SIBLING_MAP_START -->
- **`eks-best-practices`** — owns architectural / design judgement calls ("should we use X or Y", tenant isolation, ingress placement). Negatives at items 9–11 (`should_trigger: false`) are phrased as design questions and must route there, not to recon.
- **`eks-mcp-server`** — owns setup/configuration of the EKS MCP server itself. Negative at item 12 asks how to install the MCP server locally, which is a meta-tooling question, not a cluster recon request.
- **`eks-upgrade-check`** — owns structured upgrade-readiness assessments (score, blockers, remediation report). Negative at item 14 asks for a readiness score and blocker list, which is an assessment request, not a discovery pass. The discriminator: if the user wants a scored go/no-go verdict, route to `eks-upgrade-check`; if they want to understand what's deployed first, it's recon.
- **Generic / non-EKS** — pure Kubernetes-internals questions with no EKS hook. Negative at item 13 is a sanity check that recon does not fire on controller-level Kubernetes questions.
- **`eks-upgrade-check`** — owns upgrade readiness scoring ("score my upgrade readiness" wants a scored report, not a discovery inventory). Negatives at items 14, 16 enforce this.
- **`eks-operation-review`** — owns operational maturity scoring ("rate my ops posture GREEN/AMBER/RED" is a structured review, not reconnaissance). Negative at item 15 enforces this.
- **`eks-platform-engineering`** (building an Internal Developer Platform / self-service on EKS) — negative 17 ("Catalog our services in a Backstage dev…").
- **`eks-design`** (design document generation — ADRs, Mermaid diagrams, architecture scoring) — negatives 18, 19 ("Design a new EKS architecture…", "Create a security architecture document…").
- **`eks-build`** (EKS Terraform code generation — full project scaffold, Pattern 2a/2b) — negatives 20, 21 ("Generate Terraform code for…", "Build an EKS Terraform project…").
- **`eks-ingress-migration`** (assesses/plans migrating off the NGINX ingress controller to Gateway API / ALB / ATX) — negative 23 ("map nginx Ingress to HTTPRoute, flag no-Gateway-API-equivalent annotations"). Recon inventories what's deployed; ingress-migration evaluates how to move the ingress layer off nginx.
<!-- SIBLING_MAP_END -->

## Live-cluster caveat

Both prompts in `evals.json` describe realistic recon tasks against whichever EKS cluster the sandbox is pointed at via `KUBECONFIG` + AWS creds. They carry `"live_only": true` and the task runner skips them unless `--include-live-only` is passed along with a read-only `KUBECONFIG` and a scoped AWS session (Describe/List/Get only). The sandbox denies writes at the API-server level, not via convention, so running these evals is safe against a real cluster.

The `triggering.json` evals (run via `run_triggering.py`) are unaffected — they test description-fit only and never invoke cluster tooling.

## How to run

From `misc/evals/`:
- `make validate-eks-recon` — frontmatter + 64/1024-char limits (deterministic)
- `make triggering-eks-recon` — triggering accuracy score (LIVE)
- `make task-eks-recon` — task evals with grader (LIVE)
- `make process-eks-recon` — process assertions against latest trajectory (deterministic)
- `make artifact-eks-recon` — artifact validation against outputs/ (deterministic)
- `make composite-eks-recon` — weighted composite score + letter grade (deterministic)
- `make snapshot-eks-recon` — freeze current scores as baseline
- `make regression-eks-recon` — compare against baseline, report delta

See `misc/evals/README.md` for the full capability catalogue (A–K) and `.skilleval.yaml` for weight configuration.
