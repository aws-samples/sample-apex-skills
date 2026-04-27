---
name: steering-workflow-creator
description: Author a new steering workflow for any AWS service and pair it with a matching slash-command shim. Use when the user asks to create a steering workflow, add a workflow to apex, standardize steering, write a new workflow for EKS / RDS / Lambda / IAM / any AWS service, or build a phased playbook that plugs into a service hub. Covers the convention (frontmatter, header block, required sections), tool routing (knowledge vs. live MCP vs. setup-bridge), and the lint pass before handoff.
---

# Steering Workflow Creator

A meta-skill for authoring steering workflows — the phased playbooks under `steering/workflows/` that an agent reads top to bottom to conduct a structured engagement (design review, upgrade, cost review, and the like). This skill teaches you how to write one. It is not itself a workflow — don't follow it to review a cluster or upgrade anything.

The repo targets every AWS service over time. EKS is the bootstrap domain, not the target. The convention and the routing tree below are deliberately service-agnostic; an EKS worked example lives at `@references/examples/eks.md` only to show the shape, not to pin the pattern to one service.

## When to use this skill

Most tasks that sound like "add something to steering" are actually one of two very different things. Pick the right one before you start — the cost of discovering the answer after you've written 300 lines is high.

**Decision matrix — is this a skill or a steering workflow?**

| Signal in the user's ask | Build a skill | Build a workflow |
|---|---|---|
| Static domain knowledge, best practices, reference material | yes | no |
| Phased engagement with STOP gates and user checkpoints | no | yes |
| Tied to a specific lifecycle stage (Day 0 / 1 / 2) | no | yes |
| Mutation with an access model and blast-radius contract | no | yes |
| Reusable from many different workflows | yes | no |
| The output is an opinionated report for a human to act on | usually no | yes |

If the ask fits both columns, it's usually a knowledge skill plus a workflow that *uses* the skill. Write them as two artifacts. Don't smuggle phased engagement into a skill, and don't smuggle static reference content into a workflow — both directions silently lose.

**When NOT to use this skill:**

- Tweaking an existing workflow — just edit the file. The convention lives in `@references/convention.md` if you need to double-check a rule, and `scripts/quick_validate.py` lints in isolation.
- Adding a command shim on top of a workflow that already exists — copy a sibling in `steering/commands/apex/` and go.
- Pure slash-command authoring with no workflow behind it — that's a command-shim exercise, not steering.

## Capture intent

Before drafting anything, get crisp answers to five questions. If the author can't answer them cold, the workflow probably isn't shaped well enough yet — slow down.

1. **Which hub does this workflow plug into?** Every workflow has a `Part of:` hub. For EKS that's `steering/eks.md`; future services will grow their own hubs. If there is no hub yet, author the hub first — an orphaned workflow is not reachable.
2. **Which lifecycle phase — Day 0, Day 1, or Day 2?** Day 0 is architect, Day 1 is build, Day 2 is operate. The hub groups workflows by this marker, so pick one and commit.
3. **What is the primary knowledge skill this workflow leans on?** Name it. If the skill doesn't exist yet, pause and create it first — the workflow will be thin without the brain behind it.
4. **What is the access model?** `read-only`, `advisory`, or `mutating (with gates)`. This is a contract with the user about blast radius, so say it out loud before drafting.
5. **What AWS service does this target?** The answer drives which example under `@references/examples/` applies and which MCP setup-bridge skill to pair with.

One anti-overfitting note: if the author can't name a hub, the workflow may not belong in steering at all. Steering workflows are engagement structure plugged into a service; if there's no service shape, the artifact you want is probably a skill or a generic playbook somewhere else.

## Draft the workflow

Phase-two work: get a full draft on disk that satisfies the convention.

Apply `@references/convention.md` as the non-negotiable spec. It defines the frontmatter keys, the four-line header block, the five required H2 sections in order, the STOP-gate syntax, cross-link style, and the ~450-line soft cap. Treat it as authoritative — where `design.md` and `upgrade.md` disagree, the convention picks the stricter of the two, and your new workflow follows the convention, not the drift.

Start from `@assets/workflow-skeleton.md`. Copy it into `steering/workflows/<name>.md` and edit in place — do not rewrite from scratch. The skeleton is also the linter's conforming exemplar, so every section is there for a reason.

**Fill the routing table first, phases second.** It's tempting to start on Phase 1 prose because it's the most tangible part. Resist. The `## How to Route Requests` table forces you to enumerate the concrete user intents this workflow handles — four to seven of them — before sinking time into phase content you might throw away. If you can't list four distinct intents with different phase paths, the workflow probably doesn't have enough shape to justify being a workflow; go back to Capture intent.

Once the routing table is solid, draft the phases it points at. Each phase gets a one-paragraph preamble, the required inputs, concrete commands or routing guidance, and an explicit `**STOP.** ...` gate before any irreversible action or handoff. The STOP marker's exact spelling matters — it's how the linter finds gates and how the agent sees them at a glance.

## Wire tool routing

Phase-three work: every phase becomes a routing decision about where its information comes from.

Apply `@references/tool-routing.md` to each phase. The tree has three sources — knowledge skill, live MCP tools, skill-as-setup-bridge — and three steps at most. For every phase, annotate the source with a single line right under the heading:

```
Source: knowledge
Source: live
Source: either (framework from <skill>; specifics from live)
```

A phase with no annotation defaults to `knowledge`, which is the safer misread but still a misread — don't rely on the default, write the annotation.

**Every `live` phase needs a named CLI fallback.** Not "use the AWS CLI," not "see the docs" — the exact command. The agent invents bad CLI syntax with surprising frequency; naming the command pins the behavior. The fallback lives inline in the phase, not in an appendix.

**For every `live` phase, pick the setup-bridge skill for this service.** For EKS, that's `eks-mcp-server`. Future services will grow their own analogous bridges. The bridge is the recovery path when MCP tools aren't in the available-tools list; the CLI fallback is the recovery path when the bridge isn't feasible. Chain them in that order.

EKS-flavored workflows? See `@references/examples/eks.md` — it shows the `Source:` annotation, the MCP path, and the CLI fallback for each canonical EKS phase shape. Note that the EKS example is a worked case, not the shape all workflows must take; the rule is the tree in `tool-routing.md`, and the EKS file is one of many siblings the examples directory will eventually carry.

**If you are authoring for a service with no worked example yet** — RDS, Lambda, IAM, anything new — add a sibling file under `references/examples/<service>.md` as part of your work. Use the EKS file as the shape: list the service's discovery skill, its knowledge skill(s), its MCP setup-bridge, and a cheat-sheet of `Source:` annotations for common phase intents. This is how the pattern library grows; skip it and the next author rediscovers what you learned.

## Pair with a command shim

Phase-four work: emit the matching `steering/commands/apex/<name>.md` slash-command shim. The shim is how users reach the workflow — without it the workflow exists on disk but is effectively unreachable.

Start from `@assets/command-shim-skeleton.md`. The shim is a thin file: two-key YAML frontmatter plus three tags — `<objective>`, `<execution_context>`, `<process>`. The tag names are fixed; the Claude Code runtime looks for exactly those three. Inventing a fourth tag doesn't break anything, but it adds variance across shims, so don't.

Cross-reference the real shims under `steering/commands/apex/` for tone — `eks-design.md`, `eks-upgrade.md`, `eks.md` are the current examples. Mirror their action-oriented description style and their one-paragraph `<process>` block.

One small note: the existing shims in the repo use `--` rather than the em-dash `—` in a few places. That is drift; the convention going forward is em-dash everywhere, in both the workflow and the shim. New shims conform to the convention, not to the drift.

## Validate

Phase-five work: before handoff, lint and self-check.

Run the linter:

```bash
python scripts/quick_validate.py <path-to-your-draft-workflow.md>
```

It checks the mechanical rules — frontmatter keys, header-block lines in order, required H2 sections in order, STOP-gate spelling, em-dash not double-hyphen, arrow direction, `Source:` annotations, named CLI fallbacks on `live` phases, relative cross-links, the ~450-line soft cap. Most of these are one-line fixes.

Then walk the Quality Checklist from the workflow itself — yes, the checklist you just wrote. The point of promoting it from optional to required is that workflows produce recommendations users act on, and without a self-grade pass the agent has no forcing function to catch its own weakly-justified output. Run the checklist mentally against a realistic sample user request; if any item scores poorly, that's a phase to revisit.

If the linter fails and the fix isn't obvious, read `@references/anti-patterns.md` — most failures map to one of the catalogued drifts observed between `design.md` and `upgrade.md`. The linter's error messages quote the anti-pattern entries for exactly this reason.

## Iterate

Phase-six work: tighten, not gold-plate.

Common drifts — `--` creeping back in, STOP gates written inline rather than bolded, `inclusion: manual` accidentally copied from a hub file, live phases with hand-waved fallbacks — are catalogued in `@references/anti-patterns.md`. When a review comment or a linter run turns up a surprise, check the anti-patterns file first; the fix pattern is usually already written.

Keep the workflow under ~450 lines. Past that, the agent's attention gets diluted and the phase gates lose weight. If you are bumping the cap, the workflow is probably two workflows (the routing table will usually show it — two modes that never co-occur) or it is smuggling skill content that should move into the relevant skill's `references/` tree.

Anti-overfitting: before declaring done, run the workflow mentally against three or four realistic user phrasings — not the tidy phrasings you had in mind when drafting the routing table, but the casual, partial, slightly-off phrasings a real user would type. If the routing table can't absorb them, rework the table, not the phases. The routing table is the contract with the user; the phases are the implementation.
