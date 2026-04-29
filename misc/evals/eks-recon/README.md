# `eks-recon` evals

## What these evals target

These artifacts exercise the `eks-recon` skill, whose job is read-only discovery of an existing EKS cluster: current version, compute strategy (Karpenter / MNG / Auto Mode / Fargate), IaC tooling, CI/CD pipelines, add-on inventory, networking, security posture, and observability. `triggering.json` checks that the skill fires on realistic recon phrasings and does NOT fire on near-miss requests that belong to its sibling skills. `evals.json` sketches two end-to-end recon tasks (upgrade-prep context and a team handoff) that a good recon response must cover.

## Neighbour-skill disambiguation

<!-- SIBLING_MAP_START -->
- **`eks-best-practices`** — owns architectural / design judgement calls ("should we use X or Y", tenant isolation, ingress placement). Negatives at items 9–11 (`should_trigger: false`) are phrased as design questions and must route there, not to recon.
- **`eks-upgrader`** — owns executing upgrades and component-specific upgrade procedures (in-place, blue-green, Karpenter bumps). Negatives at items 12–14 ask for step-by-step upgrade runbooks and belong to the upgrader, not recon. Note: item 2 in the positives ("about to upgrade, give me context first") IS recon because it asks for pre-upgrade discovery rather than upgrade execution.
- **`eks-mcp-server`** — owns setup/configuration of the EKS MCP server itself. Negative at item 15 asks how to install the MCP server locally, which is a meta-tooling question, not a cluster recon request.
- **Generic / non-EKS** — pure Kubernetes-internals questions with no EKS hook. Negative at item 16 is a sanity check that recon does not fire on controller-level Kubernetes questions.
<!-- SIBLING_MAP_END -->

## Live-cluster caveat

Both prompts in `evals.json` describe realistic recon tasks against whichever EKS cluster the sandbox is pointed at via `KUBECONFIG` + AWS creds. They carry `"live_only": true` and the task runner skips them unless `--include-live-only` is passed along with a read-only `KUBECONFIG` and a scoped AWS session (Describe/List/Get only). The sandbox denies writes at the API-server level, not via convention, so running these evals is safe against a real cluster.

The `triggering.json` evals (run via `run_triggering.py`) are unaffected — they test description-fit only and never invoke cluster tooling.

## How to run

See `misc/evals/README.md` for the full invocation surface. From `misc/evals/` the relevant Makefile targets are:

```bash
make validate-eks-recon triggering-eks-recon optimize-eks-recon
```
