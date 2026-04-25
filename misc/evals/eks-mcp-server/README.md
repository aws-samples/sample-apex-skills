# eks-mcp-server evals

## What these evals target

These artifacts exercise the `eks-mcp-server` skill, which is **meta**: it is about installing, configuring, and troubleshooting the EKS MCP Server itself (the bridge that lets an AI assistant reach a live EKS cluster). `triggering.json` checks that Claude activates this skill for setup / config / auth-failure prompts and stays away from requests that merely **use** the MCP tools to do cluster work. `evals.json` checks that, once activated, Claude produces correct setup and IAM-troubleshooting guidance. Explicit contrast: this skill is **not** about using MCP tools to inspect, upgrade, or architect a cluster — those tasks belong to `eks-recon`, `eks-upgrader`, and `eks-best-practices` respectively.

## Neighbour-skill disambiguation

- **eks-recon (most important edge — the recon-boundary):** "inventory my cluster", "what version am I running", "list my node groups", "check IMDSv2" all *use* the MCP tools and route to `eks-recon`. Only "configure the MCP server so Claude can see my cluster" (or "tools aren't appearing", "AccessDenied on eks-mcp:InvokeMcp", "where does mcp.json go") routes here. This boundary is the highest overmapping risk and negative cases 1–4 in `triggering.json` enforce it.
- **eks-upgrader:** Actually performing an EKS version upgrade or an add-on upgrade (Karpenter, Istio, CoreDNS) is upgrader territory. The MCP server is a *tool used during* the upgrade, not the subject. Negatives 5–6 enforce this.
- **eks-best-practices:** Architecture and design decisions ("should we use Karpenter or Auto Mode", multi-tenant platform design) are best-practices territory. Negative 7 enforces this.
- **Generic MCP / unrelated:** "How do I build my own MCP server in Python" is about MCP-the-protocol, not the EKS MCP Server — it should not trigger this skill. Negative 8 enforces this.

## Live-MCP caveat

The two eval prompts in `evals.json` are about **talking about** the EKS MCP Server — explaining how to install it and diagnosing IAM errors when calling it. Answering them requires no live MCP tools and no real EKS cluster; the model should respond from the skill's reference docs. Triggering evals are pure classification and are never affected by MCP availability either.

## How to run

See `misc/evals/README.md` for the full harness description and the Makefile targets (`make eval-triggering SKILL=eks-mcp-server`, `make eval-tasks SKILL=eks-mcp-server`).
