# eks-upgrader evals

## What these evals target

These evals exercise the `eks-upgrader` skill's declared scope: **executing** EKS version upgrades and producing **component-specific procedures** for Karpenter, Istio, CoreDNS, kube-proxy, VPC CNI, ingress controllers, and cluster-autoscaler — plus the in-place and blue-green procedural playbooks, add-on compatibility matrices, version end-of-support handling, and debugging of a stuck upgrade. `triggering.json` covers the decision "should this skill fire?" with near-miss negatives drawn from the three sibling skills; `evals.json` covers "when it fires, does it produce a real, sequenced, component-aware upgrade plan?". Strategy *choice* ("in-place vs blue-green, which should we pick?") is deliberately routed to `eks-best-practices` and appears only as negatives here.

## Neighbour-skill disambiguation

<!-- SIBLING_MAP_START -->
- **`eks-recon`** (discovery / "what do we have?") — negatives 9, 10, 11 ("what version am I running", "discovery pass on our EKS environment", "tell me what's deployed"). **The single most important boundary for `eks-upgrader`**: many users plan upgrades by first asking what they're running, and the skill must *not* fire on discovery intent. The rule: if the user hasn't yet committed to an upgrade action or compatibility question, it's recon.
- **`eks-best-practices`** (strategy / architecture) — negatives 12, 13, 14 ("in-place vs blue-green, which should we choose", "is blue-green worth the 2x cost", "redesigning our EKS platform for multi-tenancy"). **The second most important boundary**: `eks-upgrader` owns the *procedure* for a chosen strategy; `eks-best-practices` owns the *choice between* strategies and upgrade-friendly architecture. The rule: if the user is still deciding, it's best-practices; if they've decided and want steps, it's upgrader.
- **`eks-mcp-server`** (tooling setup) — negative 15 ("install and configure the EKS MCP server so my AI assistant can talk to my cluster"). Not an upgrade task.
- **Unrelated / non-EKS** — negative 16 ("upgrade procedure for self-managed vanilla Kubernetes on bare metal"). EKS-specific procedure is the skill's remit; generic k8s upgrades aren't.
<!-- SIBLING_MAP_END -->

## Live-MCP caveat

`eks-upgrader`'s eval prompts are intentionally advisory and documentary — both task-eval prompts are answerable from the skill's references without touching a real cluster, and no live MCP tools are required to grade them. In principle a production upgrade *would* involve live cluster inspection (Cluster Insights, deprecated-API audit-log queries, add-on versions), but we keep the eval prompts MCP-free so results are reproducible across environments that lack MCP access. Triggering evals are pure classification and are never affected by MCP availability.

## How to run

See `misc/evals/README.md` for the eval harness. Per-skill Makefile targets: `make triggering-eks-upgrader` (triggering accuracy), `make benchmark-eks-upgrader BENCHMARK_DIR=…` (aggregate `grading.json` files into `benchmark.md`).
