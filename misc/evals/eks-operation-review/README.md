# Evals — eks-operation-review

## What these evals target

These evals exercise the `eks-operation-review` skill's declared scope: **assessing** a live EKS cluster's operational posture across 10 areas (cluster lifecycle, IaC/GitOps, access/identity, observability, workload configuration, networking, autoscaling, deployment practices, operational processes, add-on management) and producing a rated GREEN/AMBER/RED report. `triggering.json` checks the decision "should this skill fire?" against the explicit-trigger boundary the upstream skill author deliberately set — assessment-shaped requests trigger; general EKS questions, troubleshooting, and other apex skills' territory do not. `evals.json` covers "when it fires, does it produce a correctly-rated, sectioned, cluster-specific report?" via a full-review and a section-scoped (networking) review against `test-old-cluster`.

## Neighbour-skill disambiguation

This skill has explicit-trigger semantics — it deliberately does NOT auto-activate on casual EKS wording. The boundary is "the user is asking for a structured assessment with ratings and a written report" vs. "the user is asking some other kind of EKS question." The negatives below test the boundary against the most common neighbouring intents.

<!-- SIBLING_MAP_START -->
- **`eks-upgrade-check`** (upgrade-readiness assessment) — negatives 9, 10 ("is my cluster ready to upgrade from 1.31 to 1.32", "score my upgrade readiness"). Both are assessment-shaped, but they ask about *upgrade readiness* specifically, not operational posture. The discriminator: upgrade-readiness scores readiness-for-upgrade on a 100-point scale; operational-review rates 10 areas of operational practice GREEN/AMBER/RED.
- **`eks-recon`** (discovery / "what do we have?") — negatives 11, 12 ("what version am I running and which add-ons do we have installed", "full reconnaissance — compute strategy, IaC tooling, CI/CD, observability stack"). The discriminator: recon answers "what's there?"; operational-review answers "is what's there in good shape?"
- **`eks-best-practices`** (architectural choices) — negative 13 ("Karpenter vs MNG for a new cluster"). Architectural decisions belong to best-practices; operational reviews assess what's already running.
- **`eks-mcp-server`** (tooling setup) — negative 14 ("install and configure the EKS MCP server"). Setting up the MCP server is a prerequisite to running the operational review, not the review itself.
- **Upgrade execution and recovery** — negative 15 ("walk me through actually upgrading my EKS cluster"). Out of scope for the assessment skill; users wanting steps to run route elsewhere.
- **Generic / non-EKS** — negative 16 ("audit my AWS account's overall security posture — IAM, S3, CloudTrail"). EKS-specific operational review is the skill's remit; broader AWS audits are out of scope.
- **`eks-platform-engineering`** (building an Internal Developer Platform / self-service on EKS) — negative 17 ("How do we measure whether our internal…").
<!-- SIBLING_MAP_END -->

The `triggering.json` positives mix two phrasing styles: assessment-language requests ("run an operational review", "audit my cluster", "EKS health check") and section-scoped natural-question forms ("check my EKS networking", "review RBAC on my cluster"). Both styles must trigger the skill. The negatives are deliberately drawn from neighbouring apex skills' territory, plus one non-EKS distractor.

## Live-MCP caveat

The two `evals.json` task prompts target `test-old-cluster` in `us-east-1` and **require live cluster access plus the EKS MCP server** (`awslabs.eks-mcp-server`). The skill's pre-flight Action 3 explicitly verifies MCP connectivity before proceeding, and most of the 10-section checks call `list_k8s_resources` or related MCP tools. Running these evals end-to-end is therefore live and MCP-dependent — not fixture-replayable. The optional `awslabs.aws-documentation-mcp-server` is not required; the skill's `references/report-generation.md` already ships a pre-verified URL reference map and explicitly deprioritizes live doc-MCP lookups.

If MCP is unavailable, the skill stops cleanly at pre-flight Action 3 with troubleshooting guidance. Triggering evals are pure classification and are never affected by MCP availability.

## How to run

From `misc/evals/`:
- `make validate-eks-operation-review` — frontmatter + 64/1024-char limits
- `make triggering-eks-operation-review` — triggering accuracy score
- `make benchmark-eks-operation-review` — aggregate task-eval stats

See `misc/evals/README.md` for the full capability catalogue (A–K).
