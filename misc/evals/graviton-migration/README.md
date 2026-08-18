# Evals — graviton-migration

## What these evals target

These artifacts exercise the `graviton-migration` skill, which OWNS the *execution* of an x86→AWS Graviton (arm64) migration: setting up the third-party Arm migration MCP server for arm64-readiness scanning, cutting Karpenter nodes over to arm64, and making CI publish multi-arch images. `triggering.json` checks that Claude activates this skill for concrete migration-execution requests (readiness scans, node cutover, multi-arch builds, "move me to Graviton") and stays away from cost-scoring, adoption-percentage, advisory "should I?", and non-Graviton MCP-setup requests that merely share keywords. `evals.json` checks that, once activated, Claude produces the correct Arm-MCP `.mcp.json`, a taint-first Karpenter v1 arm64 NodePool with a canary toleration + arm64 nodeSelector, and a multi-arch buildx CI job — all answerable from the skill's references without a live cluster.

## Neighbour-skill disambiguation

The discriminating question is *decision/number vs. execution*: anything that asks how much Graviton would save, what the current adoption is, or whether to adopt it at all routes to a sibling; only an actual move onto arm64 stays here. The Arm migration MCP server this skill sets up is also distinct from the EKS MCP server.

<!-- SIBLING_MAP_START -->
- **`eks-cost-intelligence`** (Graviton as a COST lever — savings scoring, Spot/Graviton adoption %) — negatives 11, 12 ("How much would we save if we switc…").
- **`eks-best-practices`** (advisory "should I adopt Graviton?" architecture judgment; also Karpenter consolidation/disruption tuning) — negatives 13, 17, 18 ("Should we even bother with Graviton f…").
- **`eks-mcp-server`** (setup of the EKS MCP server for cluster ops — not the Arm migration MCP) — negative 14 ("Set up the EKS MCP server so I can qu…").
- **`eks-ingress-migration`** (nginx/ingress → ALB/Gateway migration — a different "migration" that shares vocabulary) — negative 15 ("Migrate my nginx ingress over to the…").
- **`eks-upgrade-check`** (cluster Kubernetes version upgrade readiness — not an arch migration) — negative 16 ("Upgrade my EKS cluster to 1.33…").
<!-- SIBLING_MAP_END -->

The discriminator: **execution of the arm64 move** (scan → NodePool cutover → multi-arch CI) lives here; the *savings number* goes to eks-cost-intelligence, the *adopt-or-not decision* goes to eks-best-practices, and *EKS MCP setup* goes to eks-mcp-server. Negatives 15, 16, and 18 are genuinely-adjacent-but-out-of-scope traps (ingress migration → eks-ingress-migration; cluster version upgrade → eks-upgrade-check; Karpenter consolidation/disruption tuning → eks-best-practices) that share "migrate"/"Karpenter"/"cut over" vocabulary without being a Graviton migration.

## Live-MCP caveat

The three eval prompts in `evals.json` are about **producing** config and manifests — the Arm-MCP `.mcp.json`, a Karpenter NodePool + canary spec, and a GitHub Actions job. Answering them requires no live cluster, no running Arm MCP server, and no AWS calls; the model should respond from the skill's SKILL.md and reference docs. Triggering evals are pure classification and are never affected by MCP availability either.

## How to run

From `misc/evals/`:
- `make validate-graviton-migration` — frontmatter + 64/1024-char limits (deterministic)
- `make triggering-graviton-migration` — triggering accuracy score (LIVE)
- `make task-graviton-migration` — task evals with grader (LIVE)
- `make process-graviton-migration` — process assertions against latest trajectory (deterministic)
- `make artifact-graviton-migration` — artifact validation against outputs/ (deterministic)
- `make composite-graviton-migration` — weighted composite score + letter grade (deterministic)
- `make snapshot-graviton-migration` — freeze current scores as baseline
- `make regression-graviton-migration` — compare against baseline, report delta

See `misc/evals/README.md` for the full capability catalogue (A–K) and `.skilleval.yaml` for weight configuration.
