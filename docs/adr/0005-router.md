# ADR 0005: The apex router: purpose, ownership, discovery, stages, next skills, front door and eval

- **Status**: Proposed
- **Date**: 2026-10-26

## Context

`apex` is the entry skill ([ADR 0004](0004-naming.md)) and `/apex` routes into it ([ADR 0002](0002-apex-command-routes-to-apex-skill.md)). The draft router first proposed in aws-samples/sample-apex-skills#283, before this rework (commit f9eb213 on its branch), in `skills/apex/SKILL.md`, routes by intent from four tables (EKS, ECS, cross-cutting, contributor) and asks a question only on a tie between two skills or when nothing matches. It has no notion of the customer's stage, and nothing tests it against its sibling skills.

A maintainer asked for the routing design to be thought through before the router is rebuilt: how the router knows where to send a request, whether it should ask a few questions first, whether the Day 0, Day 1 and Day 2 stages from the [skill design notes](../design/skill-design.md#day-0-day-1-day-2) should group skills into families, how a customer learns which other skills could help, and how we prove that routing works. We first planned one record per question. With few records in the repo, a maintainer preferred to keep related decisions together, so this record holds every router decision and [ADR 0006](0006-skill-content-and-auto-triggering.md) holds the decisions about skill content and automatic triggering.

The facts that shaped the options:

- On Claude Code, Kiro and Codex the model first sees only each skill's name and description and picks a skill from them; the full `SKILL.md` loads only once it is chosen. None of the three documents a precedence rule when two different skill descriptions both match a request (docs read 2026-10-26; Claude Code 2.1.310, Codex 0.163.0, Kiro CLI 1.27.0).
- Claude Code and Codex also cap the whole skill listing. Claude Code's budget scales at 1% of the model's context window and drops the descriptions of the least-invoked skills first; Codex uses at most 2% of the context window (8,000 characters when the window is unknown), shortens descriptions first and may omit skills. Kiro documents only a 1,024-character limit per description. The 29 descriptions total 24,385 characters, over both budgets on a 200k-token window, so the router's description can be cut or dropped (docs read 2026-10-26).
- Stages do not fit every skill. Of the 29 skills, 11 fit one stage, 4 fit one stage only in part, 9 span stages and 4 have no stage (one tool-setup skill and three contributor skills). The router itself has no stage.
- Some skills already run their own questionnaire, for example `eks-build`.
- The repo's eval runner stages one skill per sandbox and runs on Claude Code only, so it tests each description alone, not the router against its siblings.

Options we did not take, per question:

- **When to ask first.** Route first and ask only on a tie (the draft router); a fixed short set of questions on every request; or run read-only discovery on the live platform first (which needs credentials and the customer's consent before anything is scanned). The maintainer chose to read first and ask only what is missing.
- **Stages.** No stages; stages that drive routing (detect the stage first, then route within it), which sends a customer to the wrong family whenever the stage guess is wrong; or stages used only inside runbooks. The maintainer chose labels plus a stage hint.
- **Who owns routing.** Each skill's description, with no router precedence; AGENTS.md or per-harness configuration, which a skills-folder-only copy does not have; or a mix. The maintainer chose the router.
- **Where the eval runs.** Local and maintainer-run only; CI on Claude Code only; or CI only when a skill description changes. The maintainer chose CI on all three harnesses.

## Decision

**What routing is for.** Routing succeeds for a customer when:

1. A plain request that names no skill (for example "we are moving our app to EKS next quarter") lands in the right skill or runbook on each of Claude Code, Kiro and Codex, and the customer is told in one line which one and why.
2. When the request is unclear, the customer is asked a small number of questions, grouped in one turn, and is not asked what their own files already answer.
3. The customer learns where they are (Design, Build or Operate) and which other APEX skills could help next, without being pushed into them.
4. Context carries between skills: a design's decisions reach the build and, by the note under the hand-off table, the upgrade check without being asked again.
5. The same request gets the same route on all three harnesses, and an eval shows it.

**The router owns routing.** The apex router is the one place where routing, discovery and next-skill suggestions live. The other skills keep their automatic triggering for now ([ADR 0006](0006-skill-content-and-auto-triggering.md)) (reading, to confirm: see Open).

**Discovery: ask only what is missing.** The router reads the request and the workspace first, then asks only for what the route still needs. It reads no saved platform facts: we design the router with the skills we have today, and saved facts are a later step's design. There is no fixed cap on the number of questions; discovery should not take long, but we set no arbitrary limit. When the customer names a skill, the router skips discovery and routes at once, and the agent still works out the likely stage from that choice: a customer who asks for an upgrade check is most likely in Day 2 with a cluster already running, and the work goes on from there. Questions can live both in the router and in each skill, since what to ask depends on the requirements. Step 1 of the plan designs only the router's questions; how each skill asks its own questions is settled when that skill is rebuilt (reading, to confirm: see Open).

**Stages: labels plus a stage hint.** Each skill is to carry a stage label in its description (proposed; see Open), and skills are grouped into families by stage within each platform. The labels are "Day 0 (Design)", "Day 1 (Build)" and "Day 2 (Operate)". The router infers the customer's stage and uses it as a hint: to break ties, to choose its questions and to suggest next skills. It never filters candidate skills by stage. If the routing eval shows misroutes, we revisit making the stage drive routing.

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

**Next skills: apex owns one map.** After a routed skill finishes, the router suggests next skills only when a natural next step exists: one line, one to three skills chosen by stage, never run automatically, and nothing when nothing fits. The one next-step map lives in the router, in its hand-off table (`skills/apex/SKILL.md`, section "Hand-offs and next skills"); the stage labels sit in its "Stages and families" table. The target is that standalone skills carry no next-step lists (some carry hand-off text today), and a skill run directly, without the router, gets no suggestion (reading, to confirm: see Open).

**Hand-offs carry context.** For v2.0 the router's hand-off table names what each pair of skills passes to the next. A platform memory store replaces it in v2.1: one store that holds what each skill passes to the next, in place of the table.

**Who sees what the customer is doing.** The router reads what the customer is doing only so that the agent in the session can suggest next skills. The router sends it to no system of its own.

**The front door on each harness.** Each tool reaches the router in its own way: `/apex` on Claude Code, `$apex` on Codex, and on Kiro whatever form it accepts, for example asking it to "use apex".

**The routing eval.** We will add a routing eval that runs in CI on Claude Code, Kiro and Codex (Codex through Amazon Bedrock); none ships yet.

## Consequences

- The router's own routing rules sit in one file; plain-prompt routing still depends on every sibling's description and, on this branch, on steering/eks.md and steering/apex.md, which differ on review and compare asks (aws-samples/sample-apex-skills#288, stacked after this PR, removes steering/).
- Because the other skills keep their automatic triggering, a plain request can still go straight to a sibling skill whose description matches, and no harness documents which of two matching descriptions wins (docs read 2026-10-26; Claude Code 2.1.310, Codex 0.163.0, Kiro CLI 1.27.0). The routing eval has to show how often that happens.
- The stage is a hint, not a gate, so a wrong stage guess changes a suggestion or a question, never which skills can be reached.
- Each skill's description is proposed to gain a stage label. That costs description space, which the repo caps at 1,024 characters.
- Sibling skills' own hand-off text is reconciled with the router's next-skill map as each skill is rebuilt.
- The router has to change: discovery that reads before it asks, stage inference, the stage labels, the next-skill rule in its hand-off table, and the front door per harness. This rework followed a local no-change baseline of the old router (33b5b65) and a re-check of the reworked router: 16 prompts in two prompt wrappers, router loaded explicitly, routed skill not loaded, one run each per harness; not a CI eval.
- The repo has to gain a routing eval that installs all skills together on each harness, as a customer would. It needs prompts that name no skill, ambiguous prompts whose expected result is a question, prompts per stage and per platform, negative cases, named-skill prompts, a check that the next-skill suggestion fires, and several runs per prompt. Today's runner stages one skill at a time on Claude Code only, so it does not cover this.
- The wider reasoning is in the [skill design notes](../design/skill-design.md).

## Open

- Stage map rows marked "to confirm": the labels are proposals. We first planned a separate record for them; with related decisions merged, they sit in this record (reading, to confirm).
- Named skills: the agent infers the likely stage from any named skill, as in the upgrade-check example above (reading, to confirm).
- Where questions live: "both" read as the router asks its own questions and each skill keeps its own, the skill's questions designed when that skill is rebuilt (reading, to confirm).
- Router ownership while the other skills keep automatic triggering: read as the router owning routing for `/apex` and for the requests that reach it (reading, to confirm).
- Whether the routing eval gates merges: not decided.
- How the Kiro run of the routing eval invokes the router from CI: not established. Kiro's docs (kiro.dev/docs/skills, read 2026-10-26) document `/<skill-name> <text>` in the chat input, but in our test Kiro CLI 1.27.0's non-interactive chat rejected `/apex` ("unrecognized subcommand 'apex'"); interactive mode and later CLI versions are untested, so the form the CI eval can use is still to be found.
- How the Codex run of the routing eval reaches Amazon Bedrock from CI: not established.
- The plain-prompt path is unmeasured: the smoke check loaded the router explicitly and asked only for the route in one fixed line, so the harness reaching the router on its own, the routed skill loading, the one-line notice (criterion 1) and the question path (criterion 2) are untested; the router's row choice for no-skill requests was checked.
- The skill-listing budget: whether to trim sibling descriptions or accept that some are cut or dropped; the routing eval has to cover it (not decided).
- Today's `/apex:<name>` commands, left open by [ADR 0002](0002-apex-command-routes-to-apex-skill.md): aws-samples/sample-apex-skills#285, #286 and #288, stacked after this PR, remove their command files, and only `/apex` stays.
- Routing precedence the router cannot guarantee: `skills/apex/SKILL.md` tells the model that once the router is loaded it decides the route, even when a sibling's description also matched, and, if a sibling loaded first for the same request and the route differs, to name both skills and ask the user which to use. Nothing makes a harness load the router first, so a sibling that triggers directly on a plain request runs without the router's discovery, shared rules and next-skill suggestions. The routing eval has to measure how often that happens (not decided).
- Stage labels in sibling descriptions: a maintainer chose option B, each skill naming its stage in its description. The router rework edits no other skill, so the labels live only in the router's stage family table for now; when the sibling labels land is open.
- The next-skill map's rows: the pairs in the router's hand-off table are a first draft for review. In the family table, eks-genai and eks-platform-engineering sit in Day 1 only, eks-security under any stage, and ecs-modernize, ecs-observability and ecs-devops in each family their row above names (reading, to confirm).
- Shared rule 12 in `skills/apex/SKILL.md` (when a routed skill points at a file that is not installed, name the file and go on with the skill's own folder): not decided.
- Where shared safety rules live for a sibling run directly: not decided.
