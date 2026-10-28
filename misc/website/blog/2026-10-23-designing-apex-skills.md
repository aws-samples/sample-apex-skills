---
slug: designing-apex-skills
title: "Designing APEX skills: one entry skill, standalone skills, and where runbooks live"
description: How we are redesigning APEX skills around a single entry skill and standalone knowledge and solution skills, how Day 0, Day 1 and Day 2 shape them, why every runbook moves into one place that customers can adapt, and the plan for the next major version.
authors: [apex-maintainers]
tags: [design, skills, runbooks, adr]
date: 2026-10-23
keywords: [APEX, agent skills, skill design, runbooks, ADR, platform engineering, Day 2 operations]
---

We are starting to write down how we design APEX skills: not just what each skill knows, but how the skills fit together and which parts you are meant to change. This first post covers four conversations we have had: what to call the skills, how the platform lifecycle shapes them, one question that took us two rounds to answer (where do runbooks live?), and the plan from here.

<!-- truncate -->

The full notes and the decision records are in the repo, under [`docs/`](https://github.com/aws-samples/sample-apex-skills/tree/main/docs). This post is the story behind them.

## Where we started

When we started (2026-10-23), the repo drew a clean line between knowledge and process. `skills/` holds domain knowledge. Each skill is a folder (`SKILL.md` plus references and scripts) in the open [Agent Skills](https://agentskills.io/) format, and almost all of them work on their own. `steering/` held process: the EKS hub routed your request to a workflow (design, build, upgrade check, operational review), and the workflow loaded the skills it needed. Slash commands like `/apex:eks` and `/apex:eks-design` were the doors in.

That line works, and we are keeping it, though process moves out of `steering/` and into runbooks in the `apex` skill. But two things were missing. There was no single front door, and there was no obvious place for a customer to say "this is how *we* run an upgrade".

## One entry skill, many standalone skills

The new design has one **entry skill**, `apex`: it knows the engagements APEX can run and holds the runbooks that drive them. Every other skill is a **standalone skill**, of one of two kinds. A **knowledge skill**, such as `eks-best-practices`, gives guidance and advice. A **solution skill**, such as `eks-design`, `eks-build` or `eks-cost-intelligence`, does a piece of work and hands back a result. A runbook in `apex` loads the skills it needs, step by step.

And `/apex` becomes the front door. Before step 1, `apex` was only the prefix on commands like `/apex:eks`; there was no bare `/apex`, and nothing took you straight to the APEX entry point. In the new design, `/apex` routes directly into the apex skill, which takes over routing.

The names took a few rounds. We tried **hub and children**, **hub and spoke** and **parent and child**, and none of them fit. Each implied a relationship the skills do not have: a family, inheritance, or a skill that only connects through the hub. In practice a skill works on its own and inherits nothing. So we named the skills for what they are, not for how they relate.

## Day 0, Day 1, Day 2

Our workflows already carry a lifecycle tag. **Day 0** is design and planning, **Day 1** is build and deploy, **Day 2** is everything after go-live, such as upgrades, reviews and security posture.

We are building the new design on one skill per stage first: `eks-design` for Day 0, `eks-build` for Day 1 and `eks-cost-intelligence` for Day 2, run end to end as one flow. Before them, `eks-recon` is the single-skill test.

That gives us a few rules of thumb. A solution skill usually serves one stage well. A runbook often crosses stages, because a design hands over to a build and a cost review feeds the next design, so chaining is the entry skill's job, not a standalone skill's. And Day 2 is where customization pays most: Day 0 and Day 1 follow fairly standard steps, while Day 2 depends on your change process, your tooling and your on-call model.

## Where do runbooks live?

A runbook is the step-by-step part of an engagement: what to ask, in what order, which skill to load, what to hand back.

Our first answer was: inside each skill, for example `eks-design/runbook/`. The reason was standalone use. Pick up one folder and you have everything.

A maintainer pushed for the other answer, and it won us over: give customers **one entry point**, and let them use, update and edit **every runbook in one place**. So runbooks live under the apex skill, at `skills/apex/runbooks/<skill>/`, and they come out of the other skills.

For now we group them by skill, not by task. A folder called `design/` would blur EKS and ECS design, which are different work; `eks-design/` does not. And for now only the apex skill points at runbooks, so a standalone skill never depends on `apex/runbooks/`. The one exception is the vendored `eks-operation-review`, whose sync script rewrites upstream's pointer to its runbook there.

One thing is set: a runbook is a procedure, not an information source; domain knowledge lives only in the skill, so there is one surface to maintain. Still open, and answered in steps 3 to 5: how thin each runbook gets, whether runbooks stay grouped by skill, and where a runbook that spans several skills goes.

## The runbook is the part you change

This is the idea that ties it together. The rest of a skill is domain knowledge: facts, decision frameworks, references. That should stay close to upstream, because it gets better every time we update it. The runbook is different. It is where APEX meets *your* way of working: your approval gates, your naming, your tooling. We strongly advise customizing it.

We are not enforcing that split with folder tricks. Instead, the design notes explain the decisions we made, so you can read them, understand them, and adapt or change them as you like. Having every runbook in one folder means a customer who forks the repo has one folder to review and rebase across upgrades. How `--uninstall` treats a path you changed is in the [installer README](https://github.com/aws-samples/sample-apex-skills/blob/main/misc/installer/README.md#uninstall) (Uninstall). The clone `~/.apex-skills` is a git checkout: `--update` refuses to move it while tracked files are changed, so keep runbook edits in a fork.

## The trade-off we accept

There is a cost. A standalone skill works on its own in any agent that reads the Agent Skills format, but without `apex` it has no runbook. You get the knowledge, not the guided engagement. We accept that: if you do not take the full APEX setup, you get a weaker product, and we would rather say so plainly than copy runbooks into every skill.

## The plan

We are building the next major version in nine steps. Step 0 lays the foundations: an installer release, required checks on `main` and a test cluster. Step 1 moves things to where they live: these docs, the `apex` skill and its runbooks, `/apex` routing, and steering removed (routing changes from steering include: compare asks and casual review asks ("what do you think?") go to `eks-best-practices`, and Kiro reaches the runbooks only through the `apex` skill; the full set is in [ADR 0005](https://github.com/aws-samples/sample-apex-skills/blob/main/docs/adr/0005-router.md)). Step 2 looks at how APEX fits AWS's own agentic tooling, such as agents, MCP servers and AWS Transform. Step 3 defines what an APEX skill is, on `eks-recon`, with our standards and eval strategy. Step 4 applies that to the Day 0, Day 1 and Day 2 skills, and step 5 to every other skill we own. Step 6 covers vendored skills and skills owned by others. Step 7 is the installer (dropping the steering question and flag for v2 trees), SEO, README and site, plus the contributor skill for writing new skills, which we only build once we know what a skill is. Step 8 is the release.

## What comes next

When we wrote this (2026-10-23) none of it was built; step 1 adds the apex skill, its runbooks and `/apex`, and later posts cover the rest. These notes describe where we are heading for the next major version, and they will fold into its release docs when it ships. Later posts will cover how we engineer the harness around the skills and how we evaluate them.

The decisions so far, in the repo:

- [ADR 0001: Runbooks live in one place under the apex skill](https://github.com/aws-samples/sample-apex-skills/blob/main/docs/adr/0001-runbooks-live-in-apex.md)
- [ADR 0002: `/apex` routes directly into the apex skill](https://github.com/aws-samples/sample-apex-skills/blob/main/docs/adr/0002-apex-command-routes-to-apex-skill.md)
- [ADR 0003: A standalone skill is an accepted, weaker trade-off](https://github.com/aws-samples/sample-apex-skills/blob/main/docs/adr/0003-standalone-skills-are-a-weaker-tradeoff.md)
- [ADR 0004: One entry skill, and standalone knowledge and solution skills](https://github.com/aws-samples/sample-apex-skills/blob/main/docs/adr/0004-naming.md)
- [The skill design notes](https://github.com/aws-samples/sample-apex-skills/blob/main/docs/design/skill-design.md)
