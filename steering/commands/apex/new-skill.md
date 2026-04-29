---
name: apex:new-skill
description: Onboard a new skill end-to-end — draft it, survey siblings, fan out the repo edits, scaffold and finalize the eval set, and baseline the scorecard. Bimodal — greenfield authoring or retrofit on an existing skill.
---
<objective>
Run the APEX new-skill onboarding workflow — walk the contributor through scope intake, optional skill-creator drafting, sibling-graph survey, repo fan-out, eval scaffold and finalization, and first-baseline run.
</objective>

<execution_context>
@~/.claude/apex-steering/workflows/new-skill.md
</execution_context>

<process>
Follow the new-skill workflow end-to-end. Detect mode from `skills/<name>/SKILL.md` — if it exists this is retrofit (skip Phase 2), otherwise greenfield. Use the steering-workflow-creator skill as the spec for conventions and the skill-creator skill for Phase 2 drafting in greenfield mode. Phases: 1) scope intake and mode detection, 2) draft via skill-creator (greenfield only), 3) survey sibling graph, 4) fan out repo edits, 5) scaffold evals, apply fan-out, finalize, 6) baseline and PR prep.
</process>
