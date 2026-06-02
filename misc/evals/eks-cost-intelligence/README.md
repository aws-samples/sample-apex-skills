# Evals — eks-cost-intelligence

## What these evals target

These evals exercise the `eks-cost-intelligence` skill's declared scope: **assessing** a live EKS cluster's cost efficiency across 6 dimensions (compute efficiency, Spot/Graviton adoption, networking, storage, observability, idle resources), calculating a weighted 0–100 Cost Score, and producing a prioritized report with dollar-quantified findings and ready-to-apply remediation snippets. `triggering.json` checks the decision "should this skill fire?" against the explicit-trigger boundary — cost-assessment-shaped requests trigger; advisory guidance, operational reviews, cluster discovery, and tooling setup do not.

## Neighbour-skill disambiguation

This skill has explicit-trigger semantics — it deliberately does NOT auto-activate on casual cost wording like "how do I save money on EKS?" (that's advisory guidance from `eks-best-practices`). The boundary is "the user wants a live, scored cost assessment with dollar figures" vs. "the user wants design recommendations, an operational audit, cluster discovery, or upgrade readiness."

<!-- SIBLING_MAP_START -->
- **`eks-best-practices`** — advisory cost guidance (negatives 11, 15, 17: "how should I optimize costs", "best practices for cost management", "Karpenter or MNG design recommendation"). The discriminator: best-practices gives architectural recommendations and cost levers; cost-intelligence runs a live assessment and produces dollar-quantified waste figures with a scored report.
- **`eks-operation-review`** — operational health checks (negative 12: "run an operational review"). The discriminator: operational-review rates 10 areas of operational practice GREEN/AMBER/RED; cost-intelligence quantifies dollar waste and produces a 0–100 cost efficiency score.
- **`eks-recon`** — cluster discovery (negatives 13, 18: "what version am I running", "full reconnaissance on our EKS environment"). The discriminator: recon answers "what's there?"; cost-intelligence answers "how much is it costing and where is the waste?"
- **`eks-upgrade-check`** — upgrade readiness (negative 14: "is my cluster ready to upgrade"). The discriminator: upgrade-check scores readiness-for-upgrade across 8 areas; cost-intelligence scores cost efficiency across 6 spending dimensions.
- **`eks-mcp-server`** — MCP server setup (negative 16: "set up the EKS MCP server"). The discriminator: mcp-server helps install/configure tooling; cost-intelligence uses that tooling to run a cost assessment.
<!-- SIBLING_MAP_END -->

The `triggering.json` positives (entries 0–9) use two phrasing styles: explicit cost-assessment language ("run a cost audit", "score my cluster's cost efficiency") and business-outcome forms ("justify optimization work to leadership", "internal chargebacks"). Both must trigger the skill. The negatives (entries 10–17) are deliberately drawn from neighbouring apex skills' territory — advisory cost guidance, operational reviews, discovery, upgrade readiness, MCP setup, and architectural recommendations.

## Live-MCP caveat

The skill combines live Cost Explorer data, CloudWatch utilization metrics, and Kubernetes resource analysis to produce dollar-quantified findings. Running full task evals end-to-end **requires live cluster access** plus either the EKS MCP server (`awslabs.eks-mcp-server`) or fallback AWS CLI / kubectl connectivity. The skill's pre-flight phase explicitly verifies access before proceeding.

If MCP and CLI are both unavailable, the skill stops cleanly with troubleshooting guidance. Triggering evals are pure classification and are never affected by MCP availability.

## How to run

From `misc/evals/`:
- `make validate-eks-cost-intelligence` — frontmatter + 64/1024-char limits
- `make triggering-eks-cost-intelligence` — triggering accuracy score
- `make benchmark-eks-cost-intelligence` — aggregate task-eval stats

See `misc/evals/README.md` for the full capability catalogue (A–K).
