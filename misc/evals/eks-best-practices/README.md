# `eks-best-practices` evals

## What these evals target

These inputs exercise the `eks-best-practices` skill's declared scope: EKS architecture, design, and configuration judgement calls — compute strategy (Karpenter / MNG / Fargate / Auto Mode), multi-tenant isolation, VPC/IP planning, ingress, IAM (Pod Identity / IRSA), reliability primitives (PDBs, probes, topology spread), upgrade strategy *choice* (in-place vs blue-green), cost levers, and "is this reasonable?" sanity reviews. `triggering.json` checks that the skill fires on realistic architecture prompts and stays quiet for neighbour-skill and non-EKS prompts; `evals.json` checks the quality of two representative advisory answers.

## Neighbour-skill disambiguation

The 12 negative prompts in `triggering.json` (entries 9–20, 0-indexed 8–19) are deliberate near-misses targeting sibling skills:

<!-- SIBLING_MAP_START -->
- **`eks-recon`** (discovery / "what's currently running" / pre-upgrade inventory) — negatives 9, 10, 11 ("what version am I running", "inventory what's in my EKS cluster", "snapshot of everything running").
- **`eks-mcp-server`** (installing / wiring up the MCP server itself) — negative 12 ("install the EKS MCP server and wire it up to Claude Code").
- **`eks-upgrade-check`** — owns structured upgrade-readiness assessments (readiness score, hard-blocker override, remediation report). Negative at item 15 asks for a scored assessment with blocker detection, which is an upgrade-readiness question, not an architectural best-practice question. The discriminator: if the user wants a go/no-go verdict for a specific version hop, route to `eks-upgrade-check`; if they want design guidance about upgrade strategy (in-place vs blue-green), it's best-practices.
- **Generic / non-EKS** (no architectural judgement about EKS) — negatives 13, 14 (pure Kubernetes concepts: Deployment vs StatefulSet; non-EKS managed-K8s: AKS vs GKE).
- **`eks-upgrade-check`** (upgrade readiness scoring) — negative 15 ("is my cluster ready for 1.32?" asks for a readiness *score*, not design advice).
- **`eks-operation-review`** (operational excellence audit) — negative 16 ("audit my cluster operations" is a live-cluster review, not an architecture decision).
- **`eks-platform-engineering`** (building an Internal Developer Platform / self-service platform on EKS) — negatives 17, 18 ("We want app teams to self-serve deploym…").
- **`eks-design`** (architecture design document generation — ADRs, system arch, Mermaid diagrams, validation scoring) — negatives 19, 20 ("Generate a complete EKS architecture de…").
- **`eks-build`** (EKS Terraform code generation — full project scaffold, add-ons, ArgoCD GitOps) — negatives 21, 22 ("Generate a production-ready Terraform p…").
- **`eks-cost-intelligence`** (live cost assessment) — negatives 23, 24 ("dollar figures showing exactly how much each namespace is wasting", "scored cost efficiency report for FinOps review"). The discriminator: cost-intelligence runs a live assessment producing dollar-quantified waste and a 0–100 score; best-practices gives architectural cost recommendations and design guidance.
- **`eks-ingress-migration`** (assesses/plans migrating off the NGINX ingress controller to Gateway API / ALB / ATX) — negative 25 ("audit ingress controllers, score migration off nginx to ALB"). Best-practices gives ingress design guidance; ingress-migration assesses an existing nginx estate and produces a migration plan.
<!-- SIBLING_MAP_END -->

The key discriminators for `eks-best-practices`: the prompt asks for a *decision*, *recommendation*, *tradeoff*, or *sanity check* about an EKS design surface — not a discovery scan, not an executable upgrade runbook, and not MCP tooling setup.

## Live-MCP caveat

`evals.json` prompts are intentionally advisory and scenario-described — both evals give the model enough context in the prompt text that it can produce a quality answer without reaching into a live EKS cluster via MCP tools. Running these evals does **not** require a live cluster or the EKS MCP server to be configured. Triggering evals (`triggering.json`) are matched against the skill's `description` frontmatter only and are never affected by MCP availability.

## How to run

From `misc/evals/`:
- `make validate-eks-best-practices` — frontmatter + 64/1024-char limits (deterministic)
- `make triggering-eks-best-practices` — triggering accuracy score (LIVE)
- `make task-eks-best-practices` — task evals with grader (LIVE)
- `make process-eks-best-practices` — process assertions against latest trajectory (deterministic)
- `make artifact-eks-best-practices` — artifact validation against outputs/ (deterministic)
- `make composite-eks-best-practices` — weighted composite score + letter grade (deterministic)
- `make snapshot-eks-best-practices` — freeze current scores as baseline
- `make regression-eks-best-practices` — compare against baseline, report delta

See `misc/evals/README.md` for the full capability catalogue (A–K) and `.skilleval.yaml` for weight configuration.
