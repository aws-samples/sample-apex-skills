# Evals — eks-well-architected-review

## What these evals target

These evals exercise the `eks-well-architected-review` skill's declared scope: a **deterministic** AWS Well-Architected Framework review of a live Amazon EKS cluster — collect cluster data once via `aws` and `kubectl`, score it with fixed `jq` detections across all five pillars, hold measured findings apart from governance questions, apply a coverage gate so empty or under-observed clusters cannot score well, render a self-contained Cloudscape-styled HTML report in which every finding names the resources behind its count, and hand back a prioritized plan of improvements to raise that score.

**Drift detection is not in scope.** The skill once shipped 10 baseline "drift" checks and later retired them: 8 duplicated a scored question verbatim, 2 contradicted their scored counterparts (passing on "more than zero covered" while `sec-4`/`rel-2` graded the ratio), and the resulting "10 of 10 passing" headline undercut the real verdict. Real drift needs a stored prior run to diff against, which the skill does not keep. So no positive claims drift, and the description no longer advertises it — if that capability lands later, this eval set needs a new positive, not an edited one.

The scope has three beats, and the eval set covers all three: **run the review**, **measure how far the cluster complies with the Framework**, and **say what to change**. `triggering.json` checks the decision "should this skill fire?" — requests for any of those three against a running EKS cluster trigger; the same request aimed at another AWS service, at the account as a whole, at a narrower single-concern assessment, or at improvement advice that needs no cluster does not. `evals.json` checks that the skill honours its own determinism contract: scores come from the reducer, not from the model's arithmetic.

## Neighbour-skill disambiguation

This skill has **seven neighbours**, and the fan-out is bidirectional: each one named below carries a matching `eks-well-architected-review` bullet in its own `misc/evals/<neighbour>/README.md` SIBLING_MAP plus the corresponding negatives in its `triggering.json`, added via `misc/evals/scripts/update_sibling_map.py`. Six of the seven are also named as routing exclusions in the skill's own `description:` — `eks-upgrade-check` is not, because the 1024-char limit ran out and its boundary ("is my cluster ready to upgrade?") is the least ambiguous of the seven.

An earlier revision of this file claimed a "deliberate zero-sibling decision." That was wrong on its own terms — the description named five exclusions and the PR edited a neighbour — and it contradicted repo convention, which makes sibling fan-out mandatory whenever neighbours exist (`steering/workflows/new-skill.md:82,93`; `CONTRIBUTING.md:324`; precedents `17e7466` fanning out to 4 skills and `2a2d33f` to 5).

<!-- SIBLING_MAP_START -->
- **`eks-operation-review`** (10-area operational audit rated GREEN/AMBER/RED) — negatives 16, 24 ("rate my 10 operational areas GREEN/AMBER/RED", "audit my cluster's operational posture and rate each area GREEN, AMBER or RED"). The closest collision in the repo: its description activates on "any request to audit, review, health-check, or score an EKS cluster". The discriminator: op-review rates operational *practice* across 10 areas on a 3-band scale; this scores all five WAF pillars as a severity-weighted 0–100 with a coverage gate. Tested on both sides — its `triggering.json` carries two negatives pointing here.
- **`eks-cost-intelligence`** (dollar-quantified waste across 6 spending dimensions) — negative 17 ("how much am I wasting, give me dollar figures"). The discriminator: cost-intelligence produces dollar figures; this scores cost *hygiene* as one pillar of five and explicitly disclaims dollar quantification.
- **`eks-recon`** (fact-only cluster inventory, no scoring) — negative 18 ("just tell me what's there, no scoring"). The discriminator: recon answers "what is running"; this answers "how good is it, as a number". Collection overlaps heavily; the verdict does not.
- **`eks-best-practices`** (static advisory guidance, no cluster access) — negatives 19, 20 ("best practices for EKS multi-tenancy", "how do I improve reliability in general, no need to look at my cluster"). The discriminator: best-practices answers from static knowledge; this requires a live cluster and emits a score. Negative 20 is the tightest pair in the set against positive 6 — remediation derived from this skill's own scored findings is in scope, improvement advice in the abstract is not.
- **`eks-security`** (7-layer hardening, CIS/HIPAA/PCI/FedRAMP audit prep) — negative 23 ("harden to the CIS benchmark and get ready for a HIPAA audit"). The discriminator: this skill scores 54 security questions as one pillar of five but prescribes no hardening roadmap and maps to no compliance regime.
- **`eks-design`** (design documents, Mermaid diagrams, ADRs) — negative 21 ("architecture design document with Mermaid diagrams"). The discriminator: design authors an artifact for a proposed architecture; this scores a running one. Sharpest *lexical* collision, since eks-design's own description says "guided by Well-Architected best practices".
- **Generic / non-EKS** (right review, wrong target) — negatives 12, 13, 14, 15 ("Well-Architected review on my ECS cluster", "on our AWS account", "RDS Aurora against the Framework", "serverless lens"). Not siblings — no EKS skill competes for these. The discriminator: this skill reads an EKS control plane and data plane; it has no detections for any other service and no account-wide aggregation.
- **`eks-upgrade-check`** (upgrade readiness against a target version) — negative 22 ("ready to upgrade to 1.33"). Structural twin — live assessment, 0–100 score, HTML report — but a different question. Its `SKILL.md` is **vendored from upstream and must not be edited here**; only its `misc/evals/` entry is repo-owned.
<!-- SIBLING_MAP_END -->

Indices above are **1-indexed into the full `triggering.json` list**, which is what `parse_sibling_map` expects: positives occupy 1–11, negatives 12–24.

**Vendored-skill constraint.** `eks-operation-review` and `eks-upgrade-check` are vendored (see their `UPSTREAM.md`), so their `SKILL.md` descriptions are upstream-owned and were **not** touched. Their `misc/evals/` entries are repo-owned and were updated. Only `eks-best-practices` — a native skill — had its `description:` amended to name this skill in its "scoring or auditing a live cluster" routing clause.

The discriminator across every bucket is the same: **a live EKS cluster, all five pillars, and a reproducible number**. Drop any one of the three and the request belongs elsewhere. Positives 1–11 exercise three phrasing styles — canonical framework language ("Well-Architected review", "score against the Framework", "WAFR"); compliance-shaped language ("how compliant is our cluster with the Framework"); and outcome-shaped language that never names the framework ("how does our cluster rate on operational excellence, security, reliability, performance and cost"). All three must trigger. Positive 6 covers the improvement half of the scope ("tell me what to fix first to raise the score"), positive 7 covers the named-resource lists ("show me which resources are failing each check"), positive 10 exercises `interactive` mode (governance questions batched at the end), and positive 3 exercises explicit cluster-and-region targeting.

Negative 20 is the counterweight to positive 6 and the tightest pair in the set: the skill owns *remediation derived from its own scored findings*, not generic improvement advice. "Tell me what to fix first to raise the score" needs a cluster and a prior review; "how do I improve reliability on EKS in general, no need to look at my cluster" explicitly refuses one and belongs to `eks-best-practices`.

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
