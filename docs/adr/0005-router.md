# ADR 0005: The apex router: purpose, ownership, discovery, stages, next skills, front door and eval

- **Status**: Proposed
- **Date**: 2026-10-26

## Context

`apex` is the entry skill ([ADR 0004](0004-naming.md)) and `/apex` routes into it ([ADR 0002](0002-apex-command-routes-to-apex-skill.md)). The first version of the router, in `skills/apex/SKILL.md`, routes by intent from four tables (EKS, ECS, cross-cutting, contributor) and asks a question only on a tie between two skills or when nothing matches. It has no notion of the customer's stage, it reads no saved platform facts, and nothing tests it against its sibling skills.

A maintainer asked for the routing design to be thought through before the router is rebuilt: how the router knows where to send a request, whether it should ask a few questions first, whether the Day 0, Day 1 and Day 2 stages from the [skill design notes](../design/skill-design.md#day-0-day-1-day-2) should group skills into families, how a customer learns which other skills could help, and how we prove that routing works. We first planned one record per question. With few records in the repo, a maintainer preferred to keep related decisions together, so this record holds every router decision and [ADR 0006](0006-skill-content-and-auto-triggering.md) holds the decisions about skill content and automatic triggering.

The facts that shaped the options:

- On Claude Code, Kiro and Codex the model first sees only each skill's name and description and picks a skill from them; the full `SKILL.md` loads only once it is chosen. None of the three documents a precedence rule when two different skill descriptions both match a request.
- Stages do not fit every skill. Of the 29 skills, 11 fit one stage, 4 fit one stage only in part, 9 span stages and 4 have no stage (one tool-setup skill and three contributor skills). The router itself has no stage.
- Some skills already run their own questionnaire, for example `eks-build`.
- The repo's eval runner stages one skill per sandbox and runs on Claude Code only, so it tests each description alone, not the router against its siblings.

Options we did not take, per question:

- **When to ask first.** Route first and ask only on a tie (today's router); a fixed short set of questions on every request; or run read-only discovery on the live platform first (which needs credentials and the customer's consent before anything is scanned).
- **Stages.** No stages; stages that drive routing (detect the stage first, then route within it), which sends a customer to the wrong family whenever the stage guess is wrong; or stages used only inside runbooks.
- **Who owns routing.** Each skill's description, with no router precedence; AGENTS.md or per-harness configuration, which a skills-folder-only copy does not have; or a mix.
- **Where the eval runs.** Local and maintainer-run only; CI on Claude Code only; or CI only when a skill description changes.

## Decision

**What routing is for.** Routing succeeds for a customer when:

1. A plain request that names no skill (for example "we are moving our app to EKS next quarter") lands in the right skill or runbook on each of Claude Code, Kiro and Codex, and the customer is told in one line which one and why.
2. When the request is unclear, the customer is asked a small number of questions, grouped in one turn, and is not asked what their own files already answer.
3. The customer learns where they are (Design, Build or Operate) and which other APEX skills could help next, without being pushed into them.
4. Context carries between skills: a design's decisions reach the build and the upgrade check without being asked again.
5. The same request gets the same route on all three harnesses, and an eval shows it.

**The router owns routing.** The apex router is the one place where routing, discovery and next-skill suggestions live. The other skills keep their automatic triggering for now ([ADR 0006](0006-skill-content-and-auto-triggering.md)).

**Discovery: ask only what is missing.** The router reads the request, the workspace and any saved platform facts in `.apex/` first, then asks only for what the route still needs. There is no fixed cap on the number of questions; discovery should not take long, but we set no arbitrary limit. When the customer names a skill, the router skips discovery and routes at once, and the agent still works out the likely stage from that choice: a customer who asks for an upgrade check is most likely in Day 2 with a cluster already running, and the work goes on from there. Questions can live both in the router and in each skill, since what to ask depends on the requirements. Step 1 of the plan designs only the router's questions; how each skill asks its own questions is settled when that skill is rebuilt.

**Stages: labels plus a stage hint.** Each skill carries a stage label, and skills are grouped into families by stage within each platform. The labels are "Day 0 (Design)", "Day 1 (Build)" and "Day 2 (Operate)". The router infers the customer's stage and uses it as a hint: to break ties, to choose its questions and to suggest next skills. It never filters candidate skills by stage. If the routing eval shows misroutes, we revisit making the stage drive routing.

**The starting stage map.** We start from this map. Rows marked "to confirm" do not fit one stage cleanly; their labels are proposals for review.

| skill | stage label | note |
|---|---|---|
| eks-design | Day 0 (Design) | |
| eks-best-practices | any stage (catch-all) | to confirm |
| eks-build | Day 1 (Build) | |
| eks-platform-engineering | Day 1 (Build) | partly Day 0: designs and builds a platform |
| eks-genai | Day 1 (Build) | partly: spans stages |
| eks-security | Day 0 to Day 2 | to confirm |
| eks-upgrade-check | Day 2 (Operate) | |
| eks-operation-review | Day 2 (Operate) | |
| eks-cost-intelligence | Day 2 (Operate) | |
| eks-ingress-migration | Day 2 (Operate) | |
| eks-well-architected-review | Day 2 (Operate) | |
| eks-recon | any stage (discovery before a change) | to confirm |
| eks-mcp-server | no stage (tool setup) | to confirm |
| ecs-architect | Day 0 (Design) | |
| ecs-build | Day 1 (Build) | |
| dotnet-aws-ecs | Day 1 (Build) | |
| ecs-devops | Day 1 and Day 2 | partly |
| ecs-genai | any stage | to confirm |
| ecs-modernize | Day 0 to Day 1, for an app not yet on ECS | to confirm |
| ecs-observability | Day 0 or Day 2 | to confirm |
| ecs-operation-review | Day 2 (Operate) | |
| ecs-recon | any stage (discovery before a change) | to confirm |
| ecs-security | any stage | to confirm |
| graviton-migration | Day 2 (Operate) | partly |
| terraform-skill | Day 1 (Build), cross-cutting | to confirm |
| skill-creator | no stage (contributor) | to confirm |
| update-docs | no stage (contributor) | to confirm |
| steering-workflow-creator | no stage (contributor) | to confirm |
| apex | none (the router) | |

**Next skills: apex owns one map.** After a routed skill finishes, the router suggests next skills only when a natural next step exists: one line, one to three skills chosen by stage, never run automatically, and nothing when nothing fits. The one next-step map lives in the router, in its hand-off table (`skills/apex/SKILL.md`, section "Hand-offs between skills"), together with the stage labels. Standalone skills carry no next-step lists, and a skill run directly, without the router, gets no suggestion.

**Hand-offs carry context.** For v2.0 the router's hand-off table names what each pair of skills passes to the next. A platform memory store replaces it in a later release.

**Who sees what the customer is doing.** The router reads what the customer is doing only so that the agent in the session can suggest next skills. Nothing leaves the session.

**The front door on each harness.** Each tool reaches the router in its own way: `/apex` on Claude Code, `$apex` on Codex, and on Kiro whatever form it accepts, for example asking it to "use apex".

**The routing eval.** We run a routing eval in CI on all three harnesses: Claude Code, Kiro and Codex (Codex through Amazon Bedrock). Before the router is reworked, the eval first runs once, unchanged, on today's router as a baseline.

## Consequences

- Routing logic, discovery and next-skill suggestions sit in one file, so a routing change is made in one place.
- Because the other skills keep their automatic triggering, a plain request can still go straight to a sibling skill whose description matches, and no harness documents which of two matching descriptions wins. The routing eval has to show how often that happens.
- The stage is a hint, not a gate, so a wrong stage guess changes a suggestion or a question, never which skills can be reached.
- Each skill's description gains a stage label. That costs description space, which the repo caps at 1,024 characters.
- The router has to change: discovery that reads before it asks, stage inference, the stage labels, the next-skill rule in its hand-off table, and the front door per harness. That rework follows the baseline eval.
- The repo has to gain a routing eval that installs all skills together on each harness, as a customer would. It needs prompts that name no skill, ambiguous prompts whose expected result is a question, prompts per stage and per platform, negative cases, named-skill prompts, a check that the next-skill suggestion fires, and several runs per prompt. Today's runner stages one skill at a time on Claude Code only, so it does not cover this.
- The wider reasoning is in the [skill design notes](../design/skill-design.md).

## Open

- Stage map rows marked "to confirm": the labels are proposals. We first planned a separate record for them; with related decisions merged, they sit in this record (reading, to confirm).
- Named skills: the agent infers the likely stage from any named skill, as in the upgrade-check example above (reading, to confirm).
- Where questions live: "both" read as the router asks its own questions and each skill keeps its own, the skill's questions designed when that skill is rebuilt (reading, to confirm).
- Router ownership while the other skills keep automatic triggering: read as the router owning routing for `/apex` and for the requests that reach it (reading, to confirm).
- Whether the routing eval gates merges: not decided.
- How the Kiro run of the routing eval signs in from CI: not established. In our test, Kiro CLI's non-interactive chat rejected `/apex`, so the Kiro front-door form is still to be found.
- Whether today's `/apex:<name>` commands stay as shortcuts or fold into the apex skill, left open by [ADR 0002](0002-apex-command-routes-to-apex-skill.md): not decided here.
