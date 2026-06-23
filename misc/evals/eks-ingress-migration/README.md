# Evals — eks-ingress-migration

## What these evals target

These evals exercise the skill's core scope: recognizing requests to **assess and plan a migration off the NGINX ingress controller** (to Gateway API, the AWS Load Balancer Controller, or AWS Transform) and to **score how hard that migration is**. `triggering.json` checks description-fit only — that ingress-migration prompts fire and that adjacent EKS requests (ops audits, discovery, upgrade readiness, architecture advice) do not. `evals.json` checks the task output: that a run produces a Migration Difficulty Score with an auditable breakdown, a separate re-architecture gate, and correctly tiers feature-gaps.

## Neighbour-skill disambiguation

All four neighbours are EKS-scoped and several are assessment-shaped, so the boundary is about **what is being assessed**: this skill assesses *ingress/routing portability*, not operational health, version readiness, inventory, or architecture choice.

<!-- SIBLING_MAP_START -->
- **`eks-operation-review`** (10-section operational excellence audit with GREEN/AMBER/RED ratings) — negatives 10, 11 ("operational review … GREEN/AMBER/RED", "operational posture … maturity score").
- **`eks-recon`** (live-state discovery / inventory of an EKS environment) — negatives 12, 13 ("what version … which add-ons", "full reconnaissance … IaC/CI-CD/observability").
- **`eks-upgrade-check`** (Kubernetes version upgrade-readiness scoring and deprecated-API checks) — negatives 14, 15 ("ready to upgrade 1.31 to 1.32", "deprecated APIs … next version").
- **`eks-best-practices`** (architecture/design judgement calls) — negatives 16, 17 ("Karpenter or Managed Node Groups", "best practice for Pod Security Standards").
<!-- SIBLING_MAP_END -->

The discriminator: if the user wants to move *off nginx* / change the *ingress data path* (controllers, annotations, HTTPRoute, ALB, ATX), it is this skill. If they want operational scoring (`eks-operation-review`), an inventory of what's deployed (`eks-recon`), a version-upgrade verdict (`eks-upgrade-check`), or an architecture recommendation (`eks-best-practices`), it is not.

## Live-MCP caveat

The `triggering.json` evals are description-fit only and need no cluster or MCP server. The `evals.json` task prompts carry enough context (sample ingress manifests and findings) to be graded from fixtures without a live cluster; a full end-to-end run that discovers real clusters would require the EKS MCP server (see the `eks-mcp-server` skill), but the graded expectations here do not depend on it.

## Live-MCP caveat

<REPLACE: note whether the `evals.json` tasks need a live cluster / MCP server, or whether the prompts carry enough context to be answered from fixtures alone. State explicitly whether running these evals requires MCP availability.>

## How to run

From `misc/evals/`:
- `make validate-eks-ingress-migration` — frontmatter + 64/1024-char limits (deterministic)
- `make triggering-eks-ingress-migration` — triggering accuracy score (LIVE)
- `make task-eks-ingress-migration` — task evals with grader (LIVE)
- `make process-eks-ingress-migration` — process assertions against latest trajectory (deterministic)
- `make artifact-eks-ingress-migration` — artifact validation against outputs/ (deterministic)
- `make composite-eks-ingress-migration` — weighted composite score + letter grade (deterministic)

See `misc/evals/README.md` for the full capability catalogue (A–K) and `.skilleval.yaml` for weight configuration.
