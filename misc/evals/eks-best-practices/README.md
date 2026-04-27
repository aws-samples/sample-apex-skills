# `eks-best-practices` evals

## What these evals target

These inputs exercise the `eks-best-practices` skill's declared scope: EKS architecture, design, and configuration judgement calls — compute strategy (Karpenter / MNG / Fargate / Auto Mode), multi-tenant isolation, VPC/IP planning, ingress, IAM (Pod Identity / IRSA), reliability primitives (PDBs, probes, topology spread), upgrade strategy *choice* (in-place vs blue-green), cost levers, and "is this reasonable?" sanity reviews. `triggering.json` checks that the skill fires on realistic architecture prompts and stays quiet for neighbour-skill and non-EKS prompts; `evals.json` checks the quality of two representative advisory answers.

## Neighbour-skill disambiguation

The 8 negative prompts in `triggering.json` (entries 9–16, 0-indexed 8–15) are deliberate near-misses targeting sibling skills:

<!-- SIBLING_MAP_START -->
- **`eks-recon`** (discovery / "what's currently running" / pre-upgrade inventory) — negatives 9, 10, 11 ("what version am I running", "inventory what's in my EKS cluster", "snapshot of everything running").
- **`eks-upgrader`** (actually executing an upgrade, step-by-step procedures, debugging a specific add-on upgrade failure) — negatives 12, 13 ("exact steps to upgrade control plane 1.29 → 1.30", "Karpenter v0.37 → 1.0 webhook error").
- **`eks-mcp-server`** (installing / wiring up the MCP server itself) — negative 14 ("install the EKS MCP server and wire it up to Claude Code").
- **Generic / non-EKS** (no architectural judgement about EKS) — negatives 15, 16 (pure Kubernetes concepts: Deployment vs StatefulSet; non-EKS managed-K8s: AKS vs GKE).
<!-- SIBLING_MAP_END -->

The key discriminators for `eks-best-practices`: the prompt asks for a *decision*, *recommendation*, *tradeoff*, or *sanity check* about an EKS design surface — not a discovery scan, not an executable upgrade runbook, and not MCP tooling setup.

## Live-MCP caveat

`evals.json` prompts are intentionally advisory and scenario-described — both evals give the model enough context in the prompt text that it can produce a quality answer without reaching into a live EKS cluster via MCP tools. Running these evals does **not** require a live cluster or the EKS MCP server to be configured. Triggering evals (`triggering.json`) are matched against the skill's `description` frontmatter only and are never affected by MCP availability.

## How to run

See `/workspace/sample-apex-skills/misc/evals/README.md` for the full workflow, and the top-level `Makefile` targets (`make trigger-eks-best-practices`, `make eval-eks-best-practices`) for the exact invocations.
