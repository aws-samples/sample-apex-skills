# `eks-best-practices` evals

## What these evals target

These inputs exercise the `eks-best-practices` skill's declared scope: EKS architecture, design, and configuration judgement calls — compute strategy (Karpenter / MNG / Fargate / Auto Mode), multi-tenant isolation, VPC/IP planning, ingress, IAM (Pod Identity / IRSA), reliability primitives (PDBs, probes, topology spread), upgrade strategy *choice* (in-place vs blue-green), cost levers, and "is this reasonable?" sanity reviews. `triggering.json` checks that the skill fires on realistic architecture prompts and stays quiet for neighbour-skill and non-EKS prompts; `evals.json` checks the quality of three representative advisory answers (a multi-tenant compute decision, a production-readiness review, and a surge-readiness plan for a known traffic peak).

## Neighbour-skill disambiguation

The 25 negative prompts in `triggering.json` (entries 13–37, 0-indexed 12–36) are deliberate near-misses targeting sibling skills:

<!-- SIBLING_MAP_START -->
- **`eks-recon`** (discovery / "what's currently running" / pre-upgrade inventory) — negatives 13, 14, 15 (what version am I running; inventory what's in my EKS cluster; snapshot of everything running).
- **`eks-mcp-server`** (installing / wiring up the MCP server itself) — negative 16 (install the EKS MCP server and wire it up to Claude Code).
- **Generic / non-EKS** (no architectural judgement about EKS) — negatives 17, 18 (pure Kubernetes concepts: Deployment vs StatefulSet; non-EKS managed-K8s: AKS vs GKE).
- **`eks-upgrade-check`** — negatives 19, 34. Owns structured upgrade-readiness assessments (readiness score, hard-blocker override, remediation report): entry 19 asks "ready for 1.30, give me a score" and entry 34 asks "Black Friday, run the upgrade readiness checks and give a go/no-go score" — both a scored version-hop verdict, not architectural or surge-readiness design advice. The discriminator: if the user wants a go/no-go verdict for a specific version hop, route to `eks-upgrade-check`; if they want design guidance about upgrade strategy (in-place vs blue-green) or how to prepare for a traffic peak, it's best-practices. Entry 34 specifically guards the surge-readiness overlap: getting on the latest version before a peak is an upgrade question even though it names a peak event.
- **`eks-operation-review`** — negatives 20, 33, 35. Operational excellence audit / live-cluster review with GREEN/AMBER/RED scoring: entry 20 asks to audit cluster operations, entry 33 to health-check a live cluster before the flash sale and score each area GREEN/AMBER/RED, and entry 35 to go look at a running cluster and say what's not ready. Entries 33 and 35 guard the surge-readiness overlap from both sides — 33 with explicit scoring vocab and 35 with none — both ask to inspect a *live* cluster, which is an operational review, whereas best-practices gives descriptive pre-event readiness *guidance* about a cluster it cannot see.
- **`eks-cost-intelligence`** (live cost assessment) — negatives 21, 22 (dollar figures showing exactly how much each namespace is wasting; scored cost efficiency report for a FinOps review). The discriminator: cost-intelligence runs a live assessment producing dollar-quantified waste and a 0–100 score; best-practices gives architectural cost recommendations and design guidance.
- **`eks-platform-engineering`** (building an Internal Developer Platform / self-service platform on EKS) — negatives 23, 24 (app teams self-serve via a developer portal; set up Backstage, ArgoCD, and Kargo).
- **`eks-design`** (architecture design document generation — ADRs, system arch, Mermaid diagrams, validation scoring) — negatives 25, 26 (generate a complete EKS architecture design document; score and validate this architecture).
- **`eks-build`** (EKS Terraform code generation — full project scaffold, add-ons, ArgoCD GitOps) — negatives 27, 28 (generate a production-ready Terraform project; add external-secrets and cert-manager addons to our Terraform project).
- **`eks-ingress-migration`** (assesses/plans migrating off the NGINX ingress controller to Gateway API / ALB / ATX) — negative 29 (audit ingress controllers, score migration off nginx to ALB). Best-practices gives ingress design guidance; ingress-migration assesses an existing nginx estate and produces a migration plan.
- **`eks-genai`** (self-hosting LLM/GenAI workloads — GPU vs Neuron, vLLM/Ray serving, distributed training) — negatives 30, 36 (self-hosting Llama 3 on EKS — g6e vs Inferentia2, vLLM vs Ray Serve; large-scale distributed training across GPU nodes — inter-node networking and gang scheduling). Entry 36 guards the eks-genai boundary: "distributed training" is listed by name in the exclusion clause (briefly dropped in a merge trim — which regressed this negative — then restored), so a bare distributed-training prompt must route to eks-genai, not best-practices.
- **`eks-security`** (EKS security & compliance hardening — CIS, HIPAA/PCI/FedRAMP/GDPR, Pod Identity/Access Entries, PSA, GuardDuty, image signing, audit logging) — negatives 31, 32, 37 (PHI on EKS needing a HIPAA-ready baseline; PCI-DSS hardening priority order; running the CIS benchmarks against the cluster and remediating failures). Entry 37 guards the eks-security boundary: "CIS benchmarks" is listed by name in the exclusion clause (briefly dropped in a merge trim — which regressed this negative — then restored), so a bare CIS-benchmark prompt must route to eks-security, not best-practices.
<!-- SIBLING_MAP_END -->

The key discriminators for `eks-best-practices`: the prompt asks for a *decision*, *recommendation*, *tradeoff*, or *sanity check* about an EKS design surface — not a discovery scan, not an executable upgrade runbook, and not MCP tooling setup.

## Live-MCP caveat

`evals.json` prompts are intentionally advisory and scenario-described — all three evals give the model enough context in the prompt text that it can produce a quality answer without reaching into a live EKS cluster via MCP tools. Running these evals does **not** require a live cluster or the EKS MCP server to be configured. Triggering evals (`triggering.json`) are matched against the skill's `description` frontmatter only and are never affected by MCP availability.

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
