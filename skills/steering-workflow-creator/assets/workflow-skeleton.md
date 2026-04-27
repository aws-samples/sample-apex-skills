<!--
  This file is BOTH a starter template authors copy into `steering/workflows/<name>.md`
  AND the conforming exemplar the linter validates against. If you modify it, re-run
  `python ../scripts/quick_validate.py <this-file>` before committing. Any rule in
  `../references/convention.md` that this file violates becomes a linter error for
  every future workflow — treat drift here as a repo-wide regression.
-->
---
name: <workflow-name>
description: <Day N {intent} workflow. Front-load the lifecycle phase and the concrete verbs users will type — e.g., "Day 2 cost review workflow. Discovers compute posture, scores hygiene against defaults, emits recommendations.">
---

# <Workflow Title>

> Part of: [<Hub Workflow>](../<hub>.md)
> Lifecycle: Day 0 | Day 1 | Day 2
> Skill: <primary-knowledge-skill>
> Access Model: read-only | advisory | mutating (with gates)

One paragraph framing: what this workflow accomplishes, what it does not do, and which skill it leans on. Keep it to 3–5 sentences. If the Access Model is `read-only` or `mutating`, expand it in a short follow-up section here spelling out CAN / CANNOT — see `./upgrade.md` for the pattern. Advisory workflows can skip the expansion unless the boundary is non-obvious.

## How to Route Requests

| User intent | Mode / Phase |
|---|---|
| "<Concrete verb the user types, e.g., 'Run a full review'>" | Full run → Phase 1 → 2 → 3 |
| "<Scoped variant, e.g., 'Just check <sub-domain>'>" | Scoped → Phase 1 → 2 (sub-domain only) |
| "<Quick-answer variant, e.g., 'Quick health check'>" | Summary → Phase 1 only, condensed output |

Keep this table to 4–7 rows. If you need more, the extra logic belongs as prose branching inside the phases.

## Phases

### Phase 1: <Gather context>

Source: knowledge (context framework); discovery via <discovery-skill, e.g., `../../skills/<service>-recon/SKILL.md`>

One-paragraph preamble describing what this phase produces. Name the required inputs explicitly so the agent can skip questions already answered by a prior report.

Required inputs:

- <Input 1 — e.g., resource identifier>
- <Input 2 — e.g., region>
- <Input 3 — e.g., environment tier>

Steps:

1. Delegate reconnaissance to the discovery skill. If the user has already run it, read the report and skip to step 3.
2. Confirm the gathered context back to the user in a short summary — do not quiz them on values you already have.
3. Hand off to Phase 2 with the context loaded.

**STOP.** Confirm the context summary with the user before proceeding to Phase 2.

### Phase 2: <Inspect current state>

Source: live

CLI fallback: `aws <service> <command> --<identifier> <value> --query '<jmespath>'` if MCP unavailable.

One-paragraph preamble describing which aspects of live state this phase inspects and why a wrong answer from cached knowledge would be worse than a failed live call.

MCP path (preferred):

```
<mcp_tool_name>(<arg>="<value>")
<other_mcp_tool_name>(<arg>="<value>")
```

CLI fallback (named explicitly, one per check):

```bash
aws <service> <command-1> --<arg> <value>
aws <service> <command-2> --<arg> <value>
```

If MCP is unavailable, offer the setup-bridge skill once (see `../../skills/<service>-mcp-server/SKILL.md`), then — on user decline or environment lockdown — run the CLI fallback and announce reduced confidence per `../references/tool-routing.md`.

**STOP.** Present findings and wait for user acknowledgment before any decision framing.

### Phase 3: <Frame the decision>

Source: either (framework from `<knowledge-skill>`; specifics from the Phase 1 report or live calls)

One-paragraph preamble: the decision framework comes from authored knowledge, the inputs come from this run. Weave them together — don't hand the user a generic trade-off table they have to interpret themselves.

Steps:

1. Load the decision framework from the knowledge skill.
2. Pull the specifics from the Phase 1 report (or live calls if Phase 1 was skipped).
3. Present the trade-off table with this run's values filled in.
4. Run the Quality Checklist before handoff.

**STOP.** Wait for the user's reaction before suggesting follow-up actions or chaining into a peer workflow (e.g., `./<peer-workflow>.md`).

## Defaults

| Default | Value | Override when |
|---|---|---|
| <Setting 1 — e.g., review depth> | <Default value — e.g., full> | <Condition — e.g., user specifies a scoped mode> |
| <Setting 2 — e.g., output format> | <Default value — e.g., markdown report> | <Condition — e.g., user asks for JSON> |
| <Setting 3 — e.g., severity scale> | <Default value — e.g., critical / recommended / optional> | <Condition — e.g., existing rubric in play> |

Centralize every "default" the phases reference. If a phase mentions a default, it must appear in this table — or two phases will silently disagree about the value.

## Quality Checklist

Self-grade before presenting output to the user. Each item is binary: passes or fails.

- [ ] Every Phase 1 required input is filled in — no placeholders leaked into the output.
- [ ] Each `Source: live` finding is timestamped and cites which tool produced it (MCP or CLI fallback).
- [ ] Recommendations cite this run's context — not generic advice copy-pasted from the knowledge skill.
- [ ] Every finding has a concrete next step the user can take; no "consider improving X" hand-waves.
- [ ] If CLI fallback was used, a reduced-confidence notice is attached to the affected findings.
- [ ] The output reads top-to-bottom without requiring the user to cross-reference the workflow file.

Pass threshold: 5/6. Below 4/6 means rework before presenting.

## Conversation Style

Be concise. Group related questions into a single turn — never ask one at a time when three belong together. If the user has provided a prior report or existing requirements, read them first and only ask what is missing. Explain routing when activating the workflow so the user knows which mode you picked and why. When a STOP gate fires, name the gate and the concrete thing you need from the user before proceeding — do not stall silently. Use sentence-case headings and em-dashes in prose; arrows `→` in user-facing decision language, `->` only inside code blocks that render in terminals.
