# eks-mcp-server evals

## What these evals target

These artifacts exercise the `eks-mcp-server` skill, which is **meta**: it is about installing, configuring, and troubleshooting the EKS MCP Server itself (the bridge that lets an AI assistant reach a live EKS cluster). `triggering.json` checks that Claude activates this skill for setup / config / auth-failure prompts and stays away from requests that merely **use** the MCP tools to do cluster work. `evals.json` checks that, once activated, Claude produces correct setup and IAM-troubleshooting guidance. Explicit contrast: this skill is **not** about using MCP tools to inspect or architect a cluster — those tasks belong to `eks-recon` and `eks-best-practices` respectively.

## Neighbour-skill disambiguation

<!-- SIBLING_MAP_START -->
- **eks-recon (most important edge — the recon-boundary):** "inventory my cluster", "what version am I running", "list my node groups", "check IMDSv2" all *use* the MCP tools and route to `eks-recon`. Only "configure the MCP server so Claude can see my cluster" (or "tools aren't appearing", "AccessDenied on eks-mcp:InvokeMcp", "where does mcp.json go") routes here. This boundary is the highest overmapping risk and negative cases 1–4 in `triggering.json` enforce it.
- **eks-best-practices:** Architecture and design decisions ("should we use Karpenter or Auto Mode", multi-tenant platform design) are best-practices territory. Negative 5 enforces this.
- **Generic MCP / unrelated:** "How do I build my own MCP server in Python" is about MCP-the-protocol, not the EKS MCP Server — it should not trigger this skill. Negative 6 enforces this.
- **`eks-upgrade-check`** — "can I upgrade to 1.32?" runs readiness checks, not MCP server setup. Negative 7 enforces this.
- **`eks-operation-review`** — "run an operational review" executes an assessment, not MCP configuration. Negative 8 enforces this.
- **`eks-platform-engineering`** (building an Internal Developer Platform / self-service on EKS) — negative 9 ("Wire up a self-service portal so develo…").
<!-- SIBLING_MAP_END -->

## Live-MCP caveat

The two eval prompts in `evals.json` are about **talking about** the EKS MCP Server — explaining how to install it and diagnosing IAM errors when calling it. Answering them requires no live MCP tools and no real EKS cluster; the model should respond from the skill's reference docs. Triggering evals are pure classification and are never affected by MCP availability either.

## How to run

See `misc/evals/README.md` for the full harness description. Per-skill Makefile targets: `make triggering-eks-mcp-server` (triggering accuracy), `make benchmark-eks-mcp-server BENCHMARK_DIR=…` (aggregate `grading.json` files into `benchmark.md`).
