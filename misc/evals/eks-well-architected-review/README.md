# Evals — eks-well-architected-review

## What these evals target

These evals exercise the `eks-well-architected-review` skill's declared scope: a **deterministic** AWS Well-Architected Framework review of a live Amazon EKS cluster — collect cluster data once via `aws` and `kubectl`, score it with fixed `jq` detections across all five pillars, hold measured findings apart from governance questions, apply a coverage gate so empty or under-observed clusters cannot score well, and render a self-contained Cloudscape-styled HTML report. `triggering.json` checks the decision "should this skill fire?" — requests for a pillar-scored review of a running EKS cluster trigger; the same request aimed at another AWS service, at the account as a whole, or at a narrower single-concern assessment does not. `evals.json` checks that the skill honours its own determinism contract: scores come from the reducer, not from the model's arithmetic.

## Neighbour-skill disambiguation

This skill was onboarded with a **deliberate zero-sibling decision** — it is intended to ship and be deployed standalone, as one skill that completes the whole objective, so no neighbouring skill's `triggering.json` or SIBLING_MAP was edited in its PR. Known trigger collisions are accepted rather than negotiated. The negatives below therefore fall into two buckets: other AWS services and scopes (which the skill genuinely does not cover), and the routing exclusions the skill's own `description:` asserts. The second bucket tests the description as written — it is not a claim of sibling co-ownership.

<!-- SIBLING_MAP_START -->
- **Generic / non-EKS** (same review, wrong target — other services, other scopes) — negatives 10, 11, 12, 13 ("Well-Architected review on my ECS cluster", "Well-Architected review on our AWS account", "RDS Aurora against the Framework", "serverless lens"). The discriminator: this skill reads an EKS control plane and data plane with `kubectl` and `aws eks`; it has no detections for any other service and no account-wide aggregation.
- **Declared exclusions — narrower live assessment** (single-concern scored assessments the description routes away) — negatives 14, 15, 19 ("rate my 10 operational areas GREEN/AMBER/RED", "how much am I wasting, give me dollar figures", "ready to upgrade to 1.33"). The discriminator: those return one verdict on one concern; this returns a severity-weighted 0–100 per pillar plus a technical overall, and quantifies neither dollars nor target-version readiness.
- **Declared exclusions — facts, advice, or documents** (requests that want no score at all) — negatives 16, 17, 18 ("just tell me what's there, no scoring", "best practices for EKS multi-tenancy", "architecture design document with Mermaid diagrams"). The discriminator: this skill always emits a number tied to a `jq` detection over collected cluster JSON. A request that explicitly rejects scoring, needs no cluster, or wants a design artifact is out of scope.
<!-- SIBLING_MAP_END -->

Indices above are **1-indexed into the full `triggering.json` list**, which is what `parse_sibling_map` expects: negatives occupy 10–19, positives 1–9.

The discriminator across every bucket is the same: **a live EKS cluster, all five pillars, and a reproducible number**. Drop any one of the three and the request belongs elsewhere. Positives 1–9 exercise two phrasing styles — canonical framework language ("Well-Architected review", "score against the Framework", "WAFR") and outcome-shaped language that never names the framework ("how does our cluster rate on operational excellence, security, reliability, performance and cost"). Both must trigger. Positive 8 additionally exercises `interactive` mode (governance questions batched at the end); positive 3 exercises explicit cluster-and-region targeting.

## Live-MCP caveat

The skill uses **no MCP server**. It depends on the plain `aws` CLI (authenticated), `kubectl` with access to the target cluster, `jq`, and `python3` for the report renderer — see the `compatibility:` line in `SKILL.md`.

The `evals.json` tasks **need no live cluster and no credentials.** Following the convention in `eks-cost-intelligence/evals.json`, each prompt carries its own mock collection inline — the contents `cluster.json`, `nodes.json`, `pods.json`, `deployments.json`, `fargate.json` and friends would have held after Step 2 — and instructs the skill not to fabricate anything beyond it. That keeps graded behaviour reproducible, which matters more here than for most skills: determinism is this skill's central claim, so an eval whose inputs varied run to run could not test it.

The three tasks deliberately target the paths where a scoring skill is most likely to flatter its subject:

- **`empty-cluster-must-not-score`** — the Step 4 viability precondition. Zero nodes and zero workload pods must yield `NOT VIABLE — no data plane` with no pillar numbers at all. This is the skill's core anti-inflation claim, so it is eval 1.
- **`standard-cluster-deterministic-score`** — a populated cluster, asserting the numbers come from the Step 7 reducer rather than prose arithmetic, and that the Cost pillar is labelled **cost hygiene** with Spot and Graviton named as narrative opportunities held outside the score.
- **`fargate-only-na-and-coverage-gate`** — the `na` path. EC2 and node-hardening questions on a Fargate-only cluster must score `na`, never `none`, and the 50% coverage gate must return `INSUFFICIENT` rather than a flattering number.

Triggering evals are pure classification and are likewise unaffected by cluster or credential availability.

## How to run

From `misc/evals/`:
- `make validate-eks-well-architected-review` — frontmatter + 64/1024-char limits (deterministic)
- `make triggering-eks-well-architected-review` — triggering accuracy score (LIVE)
- `make task-eks-well-architected-review` — task evals with grader (LIVE, needs a cluster)
- `make process-eks-well-architected-review` — process assertions against latest trajectory (deterministic)
- `make artifact-eks-well-architected-review` — artifact validation against outputs/ (deterministic)
- `make composite-eks-well-architected-review` — weighted composite score + letter grade (deterministic)

> **macOS note:** the `Makefile` derives its `SKILLS` list with `find -printf`, which is GNU-only. On BSD `find` the per-skill targets are not generated and these commands report `No rule to make target`. Run them from Linux or a container, or `brew install findutils` and put `gfind` ahead of `find` on `PATH`.

See `misc/evals/README.md` for the full capability catalogue (A–K) and `.skilleval.yaml` for weight configuration.
