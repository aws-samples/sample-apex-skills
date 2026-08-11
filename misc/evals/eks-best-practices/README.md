# `eks-best-practices` evals

## What these evals target

These inputs exercise the `eks-best-practices` skill's declared scope: EKS architecture, design, and configuration judgement calls — compute strategy (Karpenter / MNG / Fargate / Auto Mode), multi-tenant isolation, VPC/IP planning, ingress, IAM (Pod Identity / IRSA), reliability primitives (PDBs, probes, topology spread), upgrade strategy *choice* (in-place vs blue-green), cost levers, and "is this reasonable?" sanity reviews. `triggering.json` checks that the skill fires on realistic architecture prompts and stays quiet for neighbour-skill and non-EKS prompts; `evals.json` checks the quality of two representative advisory answers.

## Neighbour-skill disambiguation

The 22 negative prompts in `triggering.json` (entries 12–33, 0-indexed 11–32) are deliberate near-misses targeting sibling skills:

<!-- SIBLING_MAP_START -->
- **`eks-recon`** (discovery / "what's currently running" / pre-upgrade inventory) — negatives 12, 13, 14 ("what version am I running", "inventory what's in my EKS cluster", "snapshot of everything running").
- **`eks-mcp-server`** (installing / wiring up the MCP server itself) — negative 15 ("install the EKS MCP server and wire it up to Claude Code").
- **Generic / non-EKS** (no architectural judgement about EKS) — negatives 16, 17 (pure Kubernetes concepts: Deployment vs StatefulSet; non-EKS managed-K8s: AKS vs GKE).
- **`eks-upgrade-check`** — owns structured upgrade-readiness assessments (readiness score, hard-blocker override, remediation report). Negatives 18 ("is my cluster ready for 1.30? give me a score") and 33 ("Black Friday is coming, run the upgrade readiness checks and give me a go/no-go score") ask for a scored version-hop verdict, not architectural or surge-readiness design advice. The discriminator: if the user wants a go/no-go verdict for a specific version hop, route to `eks-upgrade-check`; if they want design guidance about upgrade strategy (in-place vs blue-green) or how to prepare for a traffic peak, it's best-practices. Negative 33 specifically guards the surge-readiness overlap: "get on the latest version before Black Friday" is an upgrade question even though it names a peak event.
- **`eks-operation-review`** (operational excellence audit / live-cluster review with GREEN/AMBER/RED scoring) — negatives 19 ("audit my cluster operations") and 32 ("health-check my live cluster before the flash sale and score each area GREEN/AMBER/RED"). Negative 32 specifically guards the surge-readiness overlap: best-practices gives descriptive pre-event readiness *guidance*, while a request to health-check a *live* cluster and score it is an operational review.
- **`eks-platform-engineering`** (building an Internal Developer Platform / self-service platform on EKS) — negatives 20, 21 ("We want app teams to self-serve deploym…").
- **`eks-design`** (architecture design document generation — ADRs, system arch, Mermaid diagrams, validation scoring) — negatives 22, 23 ("Generate a complete EKS architecture de…").
- **`eks-build`** (EKS Terraform code generation — full project scaffold, add-ons, ArgoCD GitOps) — negatives 24, 25 ("Generate a production-ready Terraform p…").
- **`eks-cost-intelligence`** (live cost assessment) — negatives 26, 27 ("dollar figures showing exactly how much each namespace is wasting", "scored cost efficiency report for FinOps review"). The discriminator: cost-intelligence runs a live assessment producing dollar-quantified waste and a 0–100 score; best-practices gives architectural cost recommendations and design guidance.
- **`eks-ingress-migration`** (assesses/plans migrating off the NGINX ingress controller to Gateway API / ALB / ATX) — negative 28 ("audit ingress controllers, score migration off nginx to ALB"). Best-practices gives ingress design guidance; ingress-migration assesses an existing nginx estate and produces a migration plan.
- **`eks-genai`** (self-hosting LLM/GenAI workloads — GPU vs Neuron, vLLM/Ray serving) — negative 29 ("self-hosting Llama 3 on EKS — g6e vs Inferentia2, vLLM vs Ray Serve").
- **`eks-security`** (EKS security & compliance hardening — CIS, HIPAA/PCI/FedRAMP/GDPR, Pod Identity/Access Entries, PSA, GuardDuty, image signing, audit logging) — negatives 30, 31 ("We're processing PHI on EKS and need a…").
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
