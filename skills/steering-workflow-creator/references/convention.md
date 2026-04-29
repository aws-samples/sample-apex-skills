# Steering Workflow Convention

This is the canonical spec every steering workflow in this repo must satisfy. It distills the latent shape of `steering/workflows/design.md` and `steering/workflows/upgrade.md` into a single, strict contract so new workflows stop drifting.

Treat this file as authoritative. Where the two existing workflows disagree, convention picks the stricter of the two — on the theory that the next author will read this, not the old files. If you find yourself arguing with a rule, read the "why" note attached to it before overriding — most drift is good intentions reinventing an inconsistency.

Workflows that conform to this spec can be linted mechanically (see `scripts/quick_validate.py`). Anything below that looks optional is still required unless it says "optional" explicitly.

---

## Scope of this document

- **Applies to:** files under `steering/workflows/*.md` — the phased playbooks the agent runs against a user request.
- **Does not apply to:** hub files (`steering/<service>.md`), command shims (`steering/commands/apex/*.md`), or skills (`skills/*/SKILL.md`). Hubs and shims have their own shapes, mentioned here only where they pair with a workflow.

Note on terminology: a "workflow" in this repo is a markdown file that an agent reads top to bottom to conduct a structured engagement. It is not a diagram, not a state machine artifact, not code.

---

## Frontmatter

Every workflow file starts with YAML frontmatter containing exactly two keys:

```yaml
---
name: <workflow-slug>
description: <one-sentence trigger-optimized description>
---
```

Rules:

- `name` — lowercase, hyphenated, matches the filename without extension. This is what command shims and hub tables point at.
- `description` — one sentence, front-loaded with the lifecycle phase and the concrete user intents it handles ("Day 2 upgrade workflow. Pre-flight validation, upgrade planning, guided execution with checkpoints, and post-upgrade validation."). This feeds skill/workflow triggering — be specific about the verbs users will type.
- **Do not** include `inclusion:` on workflow files. `inclusion: manual` is reserved for hub files like `steering/eks.md` that the agent loads only when routing into the service.

Why: workflows are loaded from hub routing tables and command shims, not from auto-inclusion. Adding `inclusion: manual` to a workflow is redundant at best and silently confusing at worst.

---

## Header block

Immediately after the `# Title` H1, include a blockquote header block with four lines, in this exact order:

```
> Part of: [<Hub Workflow>](../<hub>.md)
> Lifecycle: Day 0 | Day 1 | Day 2
> Skill: <primary knowledge skill>
> Access Model: read-only | advisory | mutating (with gates)
```

Rules:

- `Part of:` — relative link to the hub this workflow plugs into. Missing hub → the workflow is orphaned, fix that first.
- `Lifecycle:` — exactly one of `Day 0`, `Day 1`, or `Day 2`. You may append a short label after an em-dash (e.g., `Day 0 — Architect`, `Day 2 — Operate`), but the day marker comes first so the hub can group workflows by lifecycle phase.
- `Skill:` — the primary knowledge skill the workflow leans on. You may follow it with a `|`-separated list of frequently used reference files, but don't exceed one line. The rest of the skill tree surfaces naturally as you link into it from later sections.
- `Access Model:` — **required.** One of `read-only`, `advisory`, or `mutating (with gates)`. This is promoted from "nice to have" to mandatory because the existing `upgrade.md` carries an Access Model and `design.md` doesn't, and the absence cost readers clarity about what the agent is allowed to do.

Why each line exists:

- `Part of` grounds the workflow in a service hub so routing is reversible (the hub points to you, you point back to the hub).
- `Lifecycle` tells the agent which stage-of-ownership context to load and tells humans when this workflow is relevant.
- `Skill` names the ground truth for domain knowledge, so the agent knows where to look before it improvises.
- `Access Model` is a contract between the agent and the user about blast radius. Without it, a workflow for a high-risk operation looks indistinguishable from a workflow for a read-only review.

If the workflow is `read-only` or `mutating`, expand the Access Model inline — see `upgrade.md` for the pattern: a short section right after the header block that spells out CAN / CANNOT and the reasoning. Advisory workflows typically don't need the expansion, but add one if the boundary is non-obvious.

---

## Required H2 sections, in order

Every workflow must include these five H2 sections, in this order. Additional H2s (e.g., `## Multi-Hop Upgrades`, `## Version Support Awareness`) may follow — they do not fit this list but are fine at the end. Do not interleave them among the required five.

1. `## How to Route Requests`
2. `## Phases`
3. `## Defaults`
4. `## Quality Checklist`
5. `## Conversation Style`

Why this ordering: the agent reads top to bottom. Routing first tells it which mode to pick. Phases tell it what to do. Defaults let it fill gaps without asking. Quality Checklist is the self-grade before handoff. Conversation Style is the always-on tone rule applied across all of the above.

### 1. How to Route Requests

A markdown table mapping user intent to workflow mode or phase. Columns: `User Request | Mode | Phases` (or `User Request | What to Do`, as in `design.md`). Keep it to 4–7 rows — more than that and the routing logic belongs in prose branching inside the phases.

Why: the agent's first move on receiving a user message is to match intent to a row in this table. Without it, the agent has to infer routing from the phase sequence itself, which it does badly.

### 2. Phases

Numbered `### Phase N: <Name>` sections, each self-contained enough to read independently. Between phases (and inside a phase at a natural checkpoint), use the literal marker `**STOP.** ...` to mark gates where the agent must wait for user input before continuing.

Each phase should include:

- A one-paragraph preamble describing what this phase accomplishes.
- The required inputs for the phase (often a checklist).
- Concrete commands or routing guidance (see `tool-routing.md` for the knowledge-vs-live decision).
- An explicit STOP gate before any irreversible action or handoff to the next phase.

A `Source: knowledge | live | either` annotation near the phase heading is strongly recommended — it tells the agent (and the next author) which of the three information sources from `tool-routing.md` this phase draws from. For `Source: live` phases, name a CLI fallback so the phase degrades gracefully when MCP tools are unavailable.

Why STOP gates are spelled exactly `**STOP.** `: consistent phrasing makes them greppable for the linter and visually unmistakable for the agent. Variants like "⚠️ STOP" or "STOP:" invite drift.

### 3. Defaults

A two-column table of assumed defaults the agent applies unless the user overrides them. Format: `| Setting | Default |`. This exists so phases can say "present options, default `X`" and the reader knows exactly what `X` is.

Why: without a Defaults section, every "default" mention in the phases has to re-specify the value, which invites disagreement between phases. Centralize it.

### 4. Quality Checklist

A scoring rubric the agent runs before presenting output to the user. At minimum, include:

- Dimensions with weights (a table works well — see `design.md`).
- Pass/fix/rework thresholds.
- A short "quick self-check" bullet list for the always-true items (e.g., "Latest versions confirmed via internet search").

This is promoted from optional to required because `design.md` demonstrates it and `upgrade.md` leaves a gap where one ought to be — readers hitting `upgrade.md` first have no self-grade rubric to emulate.

Why: workflows produce recommendations the user acts on. Without a self-grade pass, the agent has no forcing function to catch its own weakly-justified outputs. The checklist is the forcing function.

### 5. Conversation Style

A short bullet list of tone and interaction rules. Examples: "Be concise. Group related questions — don't ask one at a time." / "If given existing requirements, read them first and skip answered questions." / "Explain routing when activating a workflow."

Why last: the style rules apply to everything above, but they're short and don't drive the reader's path through the document. Putting them last keeps the phase content at the top of scrollable real estate.

---

## Style rules

These are mechanical. The linter will enforce them.

- **Em-dash, not double-hyphen.** Use `—` (U+2014). Do not use `--` for parenthetical asides, arrows, or separators. `upgrade.md` drifted on this; don't copy it.
- **Sentence case for H2 headings.** `## How to Route Requests`, not `## HOW TO ROUTE REQUESTS` and not `## how to route requests`. Proper nouns keep their casing (`## Karpenter Nuances`).
- **Imperative voice in instructions.** "Run the pre-flight check" not "The user should run the pre-flight check" and not "You might run the pre-flight check."
- **STOP markers spelled `**STOP.** ...`.** Two asterisks, the word `STOP`, a period, two asterisks, a space, then the gate description. No emoji, no alternate punctuation.
- **Arrows.** Prefer `→` (U+2192) over `->` for user-facing decision arrows. In code blocks that will be shown to users, `->` is acceptable because it renders consistently across fonts.
- **Line width.** No hard wrap. Let markdown renderers reflow. Long tables are fine; long prose lines are fine.

Why all this nitpicking: these are exactly the things two authors will diverge on within a month. Pinning them now means the linter can catch 80% of future drift without human review.

---

## Cross-link style

Relative paths only. No absolute filesystem paths, no repo-root-anchored paths, no URLs to the repo's own files.

Patterns:

- To a skill: `../../skills/<skill-name>/SKILL.md` or `../../skills/<skill-name>/references/<file>.md`.
- To a peer workflow: `./<other-workflow>.md`.
- To the hub: `../<hub>.md`.
- To an external doc (AWS docs, vendor sites, etc.): full `https://` URL. This is the only case where absolute is correct.

Why relative: the repo is meant to be readable on disk, in GitHub, and inside an installed skill. Absolute paths break under at least one of those views. Relative paths survive all three.

---

## Command shim pairing

Every workflow ships with a matching `steering/commands/apex/<name>.md` slash-command shim. The shim is a thin YAML-frontmatter-plus-three-tags file:

```
---
name: apex:<workflow-name>
description: <one-sentence; mirrors the workflow description, one notch more action-oriented>
---
<objective>
One sentence: what running this command accomplishes.
</objective>

<execution_context>
@~/.claude/apex-steering/workflows/<workflow-name>.md
</execution_context>

<process>
One paragraph: detect intent, route into the workflow, name the skill(s) used.
</process>
```

The shim is not optional. A workflow without a shim cannot be invoked as a slash command, and that is how users reach it. The creator skill emits both files in the same pass for this reason.

Why the three tags are fixed: the Claude Code runtime looks for exactly `<objective>`, `<execution_context>`, and `<process>`. Inventing a fourth tag won't break anything, but it won't help either, and it introduces variance across shims that makes them harder to scan.

---

## Length ceiling

Soft cap the workflow file at ~450 lines. `upgrade.md` is 443 lines. `design.md` is 354 lines. When a workflow is growing past 450:

- First, move reference content (long checklists, version tables, long procedure blocks) into the relevant skill's `references/` tree and link to it.
- Second, split into two workflows only if the user intents cleanly separate (e.g., a hypothetical "upgrade-assessment" and "upgrade-execution" — don't do this unless the routing table already shows two distinct modes that never co-occur).

Why ~450: past that, the agent's attention gets diluted and the phase gates lose weight. The limit is soft because some services legitimately need more, but treat crossing it as a review trigger, not a default.

---

## Conforming fragment

Minimal skeleton of a workflow that satisfies this spec. Real workflows flesh each section out; this shows the shape.

```markdown
---
name: cost-review
description: Day 2 cost review workflow. Discovers cluster compute posture, scores cost hygiene against defaults, and emits actionable recommendations.
---

# Cost Review Workflow

> Part of: [APEX EKS Hub](../eks.md)
> Lifecycle: Day 2 — Operate
> Skill: eks-best-practices
> Access Model: read-only

This workflow reviews an EKS cluster's cost posture. It does not modify the cluster. All recommendations are delivered as a report the user can act on.

## How to Route Requests

| User Request | Mode | Phases |
|---|---|---|
| "Review my cluster's cost" | Full review | 1 → 2 → 3 |
| "Am I overpaying for compute?" | Scoped | 1 → 2 (compute only) |
| "Quick cost health check" | Summary | 1 only, condensed output |

## Phases

### Phase 1: Gather Context

Source: either (prefer live when MCP is available; fall back to eks-recon report).

Collect cluster name, region, compute strategy, and workload profile. Use MCP tools if available; otherwise ask the user to run `eks-recon` first.

CLI fallback: `aws eks describe-cluster --name <cluster> --query 'cluster.version'`

**STOP.** Confirm context with the user before proceeding.

### Phase 2: Score Cost Posture

Source: knowledge. Read the `eks-best-practices` cost-optimization reference and score each dimension.

### Phase 3: Deliver Findings

Present the report. Run the Quality Checklist before handing off.

**STOP.** Wait for the user's reaction before suggesting follow-up actions.

## Defaults

| Setting | Default |
|---|---|
| Review depth | Compute + autoscaling |
| Output format | Markdown report with summary table |
| Severity scale | critical / recommended / optional |

## Quality Checklist

| Dimension | Weight | What to Check |
|---|---|---|
| Coverage | 40% | Every requested domain scored |
| Specificity | 30% | Recommendations cite this cluster's context, not generic advice |
| Actionability | 30% | Each finding has a concrete next step |

Pass at 80%. Below 60% means rework before presenting.

## Conversation Style

- Be concise. Group related questions.
- If given a prior `eks-recon` report, read it first and only ask what's missing.
- Explain severity — don't just label a finding "critical", say why.
```

That fragment would pass the linter. Use it as a starting point, then flesh out phases with real commands, real STOP gates, and real references into the relevant skill tree.
