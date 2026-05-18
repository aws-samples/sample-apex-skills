# Evals — eks-upgrade-check

## What these evals target

These evals exercise the `eks-upgrade-check` skill's declared scope: **assessing** whether an EKS cluster is ready to upgrade to the next minor version, scoring it on a 100-point scale with a hard-blocker override, and producing a markdown/HTML report. `triggering.json` checks the decision "should this skill fire?" against neighbour-skill near-misses (procedure execution, discovery, architectural choices, MCP setup). `evals.json` covers "when it fires, does it produce a correctly scored, sectioned, cluster-specific report?" — exercising the clean-cluster path, the four hard-blocker classes (incompatible Karpenter, DEGRADED critical add-on, subnet IP exhaustion), and a multi-medium-finding scenario that should land in the FAIR/RISKY band without the override applying.

## Neighbour-skill disambiguation

The skill's nearest neighbour is `eks-upgrader` — both deal with EKS upgrades. The boundary: this skill answers *"is it safe to upgrade?"* and produces a score; `eks-upgrader` answers *"how do I actually upgrade?"* and produces a step-by-step procedure. The discriminator is **assess vs execute**: assessment-shaped requests (readiness, score, blockers, go/no-go) route here; procedure-shaped requests (steps, commands, mid-upgrade troubleshooting) route to `eks-upgrader`.

<!-- SIBLING_MAP_START -->
- **`eks-upgrader`** (executing the upgrade / mid-upgrade troubleshooting) — negatives 9, 10, 11 ("walk me through actually upgrading", "stuck mid-flight at the data-plane phase", "blue-green migration procedure"). The single most important boundary — most upgrade-related queries land near this line. The rule: if the user wants steps to run, it's upgrader; if they want a verdict to read, it's upgrade-check.
- **`eks-recon`** (discovery / "what do we have?") — negatives 12, 13 ("what version am I running", "full reconnaissance — compute strategy, IaC, CI/CD, observability stack"). The rule: if the user is still figuring out *what's there*, it's recon; once they're asking whether they can move it forward safely, it's upgrade-check.
- **`eks-best-practices`** (architectural choices) — negative 14 ("Karpenter vs MNG for a new cluster"). Architectural decisions are best-practices; readiness assessments are upgrade-check.
- **`eks-mcp-server`** (tooling setup) — negative 15 ("install and configure the EKS MCP server"). Not an upgrade question.
- **Generic / non-EKS** — negative 16 ("self-managed vanilla Kubernetes on bare metal"). EKS-specific assessment is the skill's remit.
<!-- SIBLING_MAP_END -->

The `triggering.json` positives are deliberately worded around assessment language ("readiness", "score", "is it safe", "blockers", "go/no-go"); the negatives are worded around procedure, discovery, design, or non-EKS targets — all common phrasings that could ambiguously pull the skill if its description over-reaches.

## Live-MCP caveat

The five `evals.json` tasks are **fully self-contained mock-data prompts**: each prompt embeds the cluster findings inline (versions, add-ons, node groups, workloads, insights) and explicitly instructs the grader to NOT run `aws` or `kubectl` commands. No live cluster, no MCP tools, no network calls are required to run or grade these evals — they exercise the scoring algorithm and report-template logic in isolation. The skill itself supports live-cluster operation in production via AWS CLI, `kubectl`, or the optional `eks-mcp-server` integration; that path is exercised through end-to-end smoke testing rather than these evals.

## How to run

From `misc/evals/`:
- `make validate-eks-upgrade-check` — frontmatter + 64/1024-char limits
- `make triggering-eks-upgrade-check` — triggering accuracy score
- `make benchmark-eks-upgrade-check` — aggregate task-eval stats

See `misc/evals/README.md` for the full capability catalogue (A–K).
