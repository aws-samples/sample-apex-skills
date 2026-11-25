# Evals — eks-sandbox-instance-selector

## What these evals target

These evals exercise the `eks-sandbox-instance-selector` skill's declared scope: **sizing** EKS nodes for AWS Nitro Sandbox pods (`isolated-sandbox` or `confidential-sandbox`), that is, which instance type, how many sandboxes per node, which limit fills first, how many nodes and what on-demand cost. `triggering.json` checks the decision "should this skill fire?": instance-type, density and cost questions about sandbox pods trigger; whether to use sandboxes and how to secure them, compute advice for ordinary pods, live cost audits and design documents do not. `evals.json` checks that the skill asks for its six required inputs when they are missing, runs the bundled script with the inputs it was given, and reports the first limit, node count, cost and caveats.

## Neighbour-skill disambiguation

The boundary is "the user has decided on Nitro Sandboxes and asks which instance type, how many per node, how many nodes or what it costs" versus "the user asks whether or how to use sandboxes, about ordinary pods, about a live cluster's spend, or for a design document".

<!-- SIBLING_MAP_START -->
- **`eks-security`** (sandboxing decisions, runtime-class enforcement, trust model and attestation) — negatives 11, 12, 13 ("Nitro Sandboxes or gVisor", "enforce the isolated-sandbox runtime class", "isolated vs confidential trust model").
- **`eks-best-practices`** (compute and sizing advice for ordinary pods) — negatives 14, 15, 16 ("Karpenter or Managed Node Groups for regular web pods", "right-sizing requests for normal pods", "Karpenter consolidation and Spot").
- **`eks-cost-intelligence`** (scored cost assessment of a live cluster) — negatives 17, 18 ("run a cost audit", "score my live cluster's cost efficiency").
- **`eks-design`** (EKS architecture design documents) — negatives 19, 20 ("architecture design document", "formal design for a new EKS cluster").
<!-- SIBLING_MAP_END -->

The discriminator: this skill computes node sizing for pods that already use a Nitro Sandbox runtime class, from bundled instance and price data; its neighbours decide on isolation, advise on ordinary compute, audit live spend or write design documents.

## Live-MCP caveat

The skill needs no live cluster, MCP server or AWS credentials: `scripts/select.py` runs offline on the bundled `data/data.json`. The `evals.json` prompts carry all inputs inline (eval 2 deliberately leaves inputs out to test the questions). Only the optional data refresh (`scripts/fetch_raw.sh`) calls AWS, read-only. Running these evals does not require MCP availability.

## How to run

From `misc/evals/`:
- `make validate-eks-sandbox-instance-selector` — frontmatter + 64/1024-char limits (deterministic)
- `make triggering-eks-sandbox-instance-selector` — triggering accuracy score (LIVE)
- `make task-eks-sandbox-instance-selector` — task evals with grader (LIVE)
- `make process-eks-sandbox-instance-selector` — process assertions against latest trajectory (deterministic)
- `make artifact-eks-sandbox-instance-selector` — artifact validation against outputs/ (deterministic)
- `make composite-eks-sandbox-instance-selector` — weighted composite score + letter grade (deterministic)

See `.skilleval.yaml` for weight configuration.
