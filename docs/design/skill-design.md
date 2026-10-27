# APEX skill design

> Status: working notes, 2026-10-23. This describes the target design for the next major version of APEX. Parts of it are decided (see the [ADRs](../adr/README.md)); parts are still open and marked as such. Where the repo works differently today, we say so.

This document is about how we design skills: how they fit together, how the lifecycle of a platform shapes them, and where the customizable parts live. We are starting simple. Over time it will grow to cover how we test and evaluate skills and the harness around them.

## Where we started (before step 1)

The repo splits knowledge from process:

- `skills/` holds domain knowledge. Each skill is a folder (`SKILL.md` plus references and scripts) in the open [Agent Skills](https://agentskills.io/) format, and almost all of them work on their own.
- `steering/` held process. The EKS hub `steering/eks.md` routes a request to a workflow in `steering/workflows/` (design, build, upgrade check, operational review and others), and each workflow loads the skills it needs. The slash commands in `steering/commands/apex/` (`/apex:eks`, `/apex:eks-design` and so on) are thin entry points into those steering files.

That split works. What it lacks is one entry point and one place where a customer adapts the process to their own way of working. The rest of this document is about closing those two gaps.

## The entry skill and standalone skills

The new design has one entry skill, and every other skill stands on its own:

- **`apex` is the entry skill.** It knows the engagements APEX can run, asks enough to pick the right one, and holds the runbooks that drive them. `/apex` takes you straight to it ([ADR 0002](../adr/0002-apex-command-routes-to-apex-skill.md)).
- **Every other skill is a standalone skill**, of one of two kinds:
  - a **knowledge skill** gives guidance and advice on a domain, for example `eks-best-practices`;
  - a **solution skill** does a piece of work and hands back a result, for example `eks-design`, `eks-build` or `eks-cost-intelligence`.

A runbook in `apex` loads the standalone skills it needs, step by step. A standalone skill does not depend on `apex` and does not inherit anything from it.

We looked at three other names before settling on this one: hub and children, hub and spoke, and parent and child. Each implied a relationship the skills do not have: a family or inheritance, or that a skill only connects through the hub. The options and the reasons are in [ADR 0004](../adr/0004-naming.md). We use these names in the docs. They do not rename any skill folder or change any skill's `name` field.

## Day 0, Day 1, Day 2

The repo already tags workflows by lifecycle: the routing table in `steering/eks.md` had a Lifecycle column, and each workflow names its stage. The three stages:

- **Day 0: design and planning.** Requirements, architecture, option comparisons, design reviews. The output is a decision and a document, not running infrastructure.
- **Day 1: build and deploy.** Turning the design into code and infrastructure, and getting the first workloads running.
- **Day 2: operate.** Everything after go-live: upgrades, operational and cost reviews, security posture, migrations.

We build and test the design on one skill per stage first: **`eks-design`** for Day 0, **`eks-build`** for Day 1 and **`eks-cost-intelligence`** for Day 2. Before them, `eks-recon` is the single-skill test of what an APEX skill is; then the three run as one Day 0 to Day 1 to Day 2 flow.

How this shapes the design:

- **Skills follow the lifecycle.** A solution skill usually serves one stage well. Naming the stage in the skill's own description helps `apex` route to it and helps a reader know what to expect.
- **Runbooks span the lifecycle.** An engagement often crosses stages: a design hands over to a build, and a cost review feeds the next design. A runbook in `apex` can chain skills across stages, which is the entry skill's job; a standalone skill may call another, but does not run an engagement across stages.
- **Day 2 is where customization pays most.** Day 0 and Day 1 follow fairly standard steps. Day 2 depends on the customer's own change process, tooling, approvals and on-call model, so Day 2 runbooks are the ones customers will adapt most.

## Runbooks

A runbook is the step-by-step part of an engagement: what to ask, in what order, which skill to load at each step, and what to hand back.

### Where they live

We looked at two places.

**In each skill**, for example `eks-design/runbook/`. This was our first choice. The appeal is standalone use: a user picks up one skill folder and has everything, runbook included.

**In one place under the entry skill**, at `skills/apex/runbooks/`. A maintainer made the stronger case: customers get one entry point, and can use, update and edit every runbook in one place.

**Decision:** runbooks live in `skills/apex/runbooks/<skill>/`, one folder per skill, and we remove runbooks from the other skills. We group them by skill for now, not by task: a task name such as "design" blurs EKS and ECS (an `eks-design` and an `ecs-design` would be different work), while a skill name does not. For now, only the `apex` skill points at runbooks; no other skill links into `apex/runbooks/`, except the vendored `eks-operation-review`, whose sync script rewrites upstream's pointer to its runbook there. See [ADR 0001](../adr/0001-runbooks-live-in-apex.md).

The steering workflows in `steering/workflows/` become these runbooks, and `steering/` goes away once they have moved.

**Still open, decided in steps 3 to 5 of the [plan](#plan):** whether runbooks stay grouped by skill, whether runbooks become thin step-by-step guides, and where a runbook that spans several skills goes.

### How customers adapt them

This is the idea going forward: the rest of a skill is domain knowledge, and the runbook is the customizable part.

- **Domain knowledge** (the standalone skills) should stay close to upstream. It is facts, decision frameworks and references, and it improves when we update it.
- **Runbooks** are where a customer fits APEX to their own use case: their approval gates, their naming, their tooling, the order they like to work in. We strongly advise customers to customize them.

We do not enforce this in the repo layout. Instead this document is where we explain the decisions we made, so readers can understand them and adapt or change them as they like. Keeping every runbook under `skills/apex/runbooks/` means a customer who forks the repo has one folder to review and rebase across upgrades. How the installer treats your edits is in the [installer README](../../misc/installer/README.md#uninstall).

### Standalone skills

A standalone skill works on its own, in any agent that reads the Agent Skills format. But without `apex` it has no runbook, so you get the knowledge without the guided engagement. We accept that as a design trade-off: users who do not take the full APEX setup get a weaker product. See [ADR 0003](../adr/0003-standalone-skills-are-a-weaker-tradeoff.md). Standalone use keeps working: a knowledge skill still gives its advice, and a solution skill keeps its references and scripts. How much of a solution skill's work runs without a runbook is decided per skill in steps 3 to 5.

## Plan

We are building the next major version in nine steps (summary). In every step we refine these notes, record decisions as ADRs and fix the open issues for the skills that step works on.

| Step | What |
|------|------|
| 0 | Foundations: installer release, required checks on `main`, a test cluster |
| 1 | Where things live (routing changes from steering: compare asks go to `eks-best-practices`, per the [apex router](../../skills/apex/SKILL.md); Kiro reaches the runbooks only through the `apex` skill): these docs and ADRs, the blog, the `apex` skill with `apex/runbooks/<skill>/`, steering removed, `/apex` routing, set up for Claude Code and Kiro, and for Codex by a manual copy |
| 2 | How APEX fits AWS's agentic tooling (agents, toolkits, MCP servers, AWS Transform), and what each skill builds on |
| 3 | What an APEX skill is, built on `eks-recon`: skill standards, design principles and the eval strategy |
| 4 | The same for Day 0, Day 1 and Day 2: `eks-design`, `eks-build`, `eks-cost-intelligence` |
| 5 | The same for every other repo-owned skill |
| 6 | Vendored skills and skills owned by others: steering removed, an issue filed per skill |
| 7 | Installer, SEO, README and site; the contributor skill for new skills, once we know what a skill is |
| 8 | Publish |

Step 1 removes the `/apex:new-skill` command and its workflow with `steering/`; we build the contributor skill in step 7, once steps 3 to 5 have settled what a skill is. Until then the steps in [CONTRIBUTING.md](../../CONTRIBUTING.md#creating-a-new-skill) (Creating a New Skill) apply. In step 1, `/apex` points to the `apex` skill, which takes over routing. Step 1 removes the `/apex:<name>` commands with `steering/`; only `/apex` stays ([ADR 0005](../adr/0005-router.md#open)).

## What comes later

These notes cover the shape of a skill. Later versions of this document will add how we engineer the harness around the skills and how we evaluate them.

Step 1 adds the `apex` skill, `skills/apex/runbooks/<skill>/` and the `/apex` route and removes `steering/`; steps 2 to 8 are not built yet. These notes fold into the release documentation when the next major version ships. Until then, this is where we record the decisions as we make them.
