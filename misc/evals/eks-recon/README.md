# `eks-recon` evals

## What these evals target

These artifacts exercise the `eks-recon` skill, whose job is read-only discovery of an existing EKS cluster: current version, compute strategy (Karpenter / MNG / Auto Mode / Fargate), IaC tooling, CI/CD pipelines, add-on inventory, networking, security posture, and observability. `triggering.json` checks that the skill fires on realistic recon phrasings and does NOT fire on near-miss requests that belong to its sibling skills. `evals.json` sketches two end-to-end recon tasks (upgrade-prep context and a team handoff) that a good recon response must cover.

## Neighbour-skill disambiguation

<!-- SIBLING_MAP_START -->
- **`eks-best-practices`** — owns architectural / design judgement calls ("should we use X or Y", tenant isolation, ingress placement). Negatives at items 9–11 (`should_trigger: false`) are phrased as design questions and must route there, not to recon.
- **`eks-upgrader`** — owns executing upgrades and component-specific upgrade procedures (in-place, blue-green, Karpenter bumps). Negatives at items 12–14 ask for step-by-step upgrade runbooks and belong to the upgrader, not recon. Note: item 2 in the positives ("about to upgrade, give me context first") IS recon because it asks for pre-upgrade discovery rather than upgrade execution.
- **`eks-mcp-server`** — owns setup/configuration of the EKS MCP server itself. Item 15 asks how to install the MCP server locally, which is a meta-tooling question, not a cluster recon request.
<!-- SIBLING_MAP_END -->

Item 16 is a pure Kubernetes-internals question with no EKS hook — a sanity negative.

## Live-MCP caveat

The two prompts in `evals.json` describe realistic recon tasks against named clusters (`payments-prod`, `data-platform-staging`). Running them end-to-end expects EKS MCP tooling (or AWS CLI + kubectl fallback) pointed at real clusters, and `files: []` is intentional — no static fixtures have been authored yet. Running the grader against a live model without MCP access will produce shallow answers; a follow-up pass should either stage fixture YAML under `files/` or flag these as MCP-required in the eval harness.

The `triggering.json` evals (run via `run_eval` / `run_loop`) are unaffected — they test description-fit only and never invoke EKS tooling.

## How to run

See `misc/evals/README.md` for the full invocation surface. From `misc/evals/` the relevant Makefile targets are:

```bash
make validate-eks-recon triggering-eks-recon optimize-eks-recon
```
