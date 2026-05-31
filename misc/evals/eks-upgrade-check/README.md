# Evals — eks-upgrade-check

## What these evals target

These evals exercise the `eks-upgrade-check` skill's declared scope: **assessing** whether an EKS cluster is ready to upgrade to the next minor version, scoring it on a 100-point scale with a hard-blocker override, and producing a markdown/HTML report. `triggering.json` checks the decision "should this skill fire?" against neighbour-skill near-misses (procedure execution, discovery, architectural choices, MCP setup). `evals.json` covers "when it fires, does it produce a correctly scored, sectioned, cluster-specific report?" — exercising the clean-cluster path, the four hard-blocker classes (incompatible Karpenter, DEGRADED critical add-on, subnet IP exhaustion), and a multi-medium-finding scenario that should land in the FAIR/RISKY band without the override applying.

## Neighbour-skill disambiguation

The most common confusion this skill needs to disambiguate is "assess my readiness to upgrade" vs. "run my upgrade." Both are EKS-upgrade phrasings; this skill owns the assessment side only — it produces a structured verdict (score, blockers, remediation) but never executes the upgrade itself.

<!-- SIBLING_MAP_START -->
- **Upgrade execution and recovery** — negatives 11, 12, 13 ("walk me through actually upgrading", "stuck mid-flight at the data-plane phase", "blue-green migration procedure"). This is the most important boundary for `eks-upgrade-check`: questions about *running* an upgrade, *executing* steps, or *recovering* from a stalled upgrade are out of scope for the readiness assessment. The discriminator: if the user wants commands to run or a procedure to follow, route elsewhere; if they want a structured verdict on whether the cluster is ready, this skill is the right fit.
- **`eks-recon`** (discovery / "what do we have?") — negatives 14, 15 ("what version am I running", "full reconnaissance — compute strategy, IaC, CI/CD, observability stack"). The rule: if the user is still figuring out *what's there*, it's recon; once they're asking whether they can move it forward safely, it's upgrade-check.
- **`eks-best-practices`** (architectural choices) — negative 16 ("Karpenter vs MNG for a new cluster"). Architectural decisions are best-practices; readiness assessments are upgrade-check.
- **`eks-mcp-server`** (tooling setup) — negative 17 ("install and configure the EKS MCP server"). Not an upgrade question.
- **Generic / non-EKS** — negative 18 ("self-managed vanilla Kubernetes on bare metal"). EKS-specific assessment is the skill's remit.
- **`eks-platform-engineering`** (building an Internal Developer Platform / self-service on EKS) — negative 19 ("Set up golden paths so app teams can sh…").
<!-- SIBLING_MAP_END -->

The `triggering.json` positives mix two phrasing styles: assessment-language requests ("readiness", "score", "is it safe", "blockers") and natural-question forms ("can I upgrade my cluster?", "are we good to go to 1.33?") that mirror the wording in `SKILL.md`'s description. Both styles must trigger the skill. The negatives are worded around procedure, discovery, design, or non-EKS targets — all common phrasings that could ambiguously pull the skill if its description over-reaches.

## Live-MCP caveat

The five `evals.json` tasks are **fully self-contained mock-data prompts**: each prompt embeds the cluster findings inline (versions, add-ons, node groups, workloads, insights) and explicitly instructs the grader to NOT run `aws` or `kubectl` commands. No live cluster, no MCP tools, no network calls are required to run or grade these evals — they exercise the scoring algorithm and report-template logic in isolation. The skill itself supports live-cluster operation in production via AWS CLI, `kubectl`, or the optional `eks-mcp-server` integration; that path is exercised through end-to-end smoke testing rather than these evals.

## How to run

From `misc/evals/`:
- `make validate-eks-upgrade-check` — frontmatter + 64/1024-char limits
- `make triggering-eks-upgrade-check` — triggering accuracy score
- `make benchmark-eks-upgrade-check` — aggregate task-eval stats

See `misc/evals/README.md` for the full capability catalogue (A–K).
