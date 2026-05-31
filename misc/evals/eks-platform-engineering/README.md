# `eks-platform-engineering` evals

## What these evals target

These inputs exercise the `eks-platform-engineering` skill's declared scope: designing and building an Internal Developer Platform (IDP) on EKS and platform-engineering decisions about developer self-service. `triggering.json` checks the skill fires on platform-build prompts (portal, golden paths, GitOps delivery, progressive delivery/promotion, infrastructure abstraction, app modeling, measuring success, AI/ML platform) and stays quiet for single-cluster EKS architecture/ops prompts and non-platform prompts. `evals.json` checks the quality of two representative platform-design answers (reference architecture + golden-path design).

## Neighbour-skill disambiguation

The 8 negative prompts in `triggering.json` (entries 9–16, 0-indexed 8–15) are deliberate near-misses targeting sibling skills. The discriminator for `eks-platform-engineering` is the *platform / self-service* angle: the user is building a paved path for **other** teams (portal, golden paths, GitOps platform), not making a one-off EKS architecture/ops decision or running a cluster scan.

<!-- SIBLING_MAP_START -->
- **`eks-best-practices`** (single-cluster EKS architecture, sizing, reliability, cost, upgrade *strategy* — no self-service/platform layer) — negatives 9, 10 ("Karpenter vs MNG vs Auto Mode data plane", "PDBs/probes/topology spread for prod reliability").
- **`eks-recon`** (discovery / "what's currently running" inventory) — negative 11 ("what version is my cluster on and which add-ons are installed").
- **`eks-upgrade-check`** (upgrade readiness *scoring*) — negative 12 ("ready to upgrade to 1.33, give me a score and blockers").
- **`eks-operation-review`** (operational excellence audit with GREEN/AMBER/RED) — negative 13 ("audit operational posture and rate each area").
- **`eks-mcp-server`** (installing / wiring the EKS MCP server itself) — negative 14 ("install the EKS MCP server and connect it to my AI assistant").
- **Generic / unrelated** (pure Kubernetes concepts, or standalone Terraform that belongs to `terraform-skill`) — negatives 15, 16 ("StatefulSet rolling updates at the controller level", "standalone Terraform module with native tests for an S3 bucket").
<!-- SIBLING_MAP_END -->

The key discriminator: the prompt asks how to build or operate a *platform* that app/ML/data teams self-serve from — portal, templates, golden paths, GitOps delivery, promotion, self-service provisioning, or platform success metrics — not a cluster-level design decision, a discovery scan, an upgrade score, an ops audit, MCP setup, or standalone IaC.

## Live-MCP caveat

`evals.json` prompts are advisory and fully scenario-described — both give the model enough context to produce a quality platform-design answer without reaching into a live cluster or MCP server. Running these evals does **not** require a live EKS cluster or the EKS MCP server. Triggering evals are matched against the skill's `description` frontmatter only and are unaffected by MCP availability. There are no `live_only` prompts.

## How to run

From `misc/evals/`:
- `make validate-eks-platform-engineering` — frontmatter + 64/1024-char limits
- `make triggering-eks-platform-engineering` — triggering accuracy score
- `make benchmark-eks-platform-engineering BENCHMARK_DIR=…` — aggregate task-eval stats

See `misc/evals/README.md` for the full capability catalogue (A–K).
