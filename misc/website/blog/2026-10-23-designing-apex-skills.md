---
slug: designing-apex-skills
title: "Designing APEX skills: one hub, many children, and where runbooks live"
description: How we are redesigning APEX skills around a single hub, how Day 0, Day 1 and Day 2 shape them, and why every runbook moves into one place that customers can adapt.
authors: [apex-maintainers]
tags: [design, skills, runbooks, adr]
date: 2026-10-23
keywords: [APEX, agent skills, skill design, runbooks, ADR, platform engineering, Day 2 operations]
---

We are starting to write down how we design APEX skills: not just what each skill knows, but how the skills fit together and which parts you are meant to change. This first post covers three conversations we have had: the shape of the skill family, how the platform lifecycle shapes it, and one question that took us two rounds to answer: where do runbooks live?

<!-- truncate -->

The full notes and the decision records are in the repo, under [`docs/`](https://github.com/aws-samples/sample-apex-skills/tree/main/docs). This post is the story behind them.

## Where we started

Today the repo draws a clean line between knowledge and process. `skills/` holds domain knowledge: each skill is a self-contained folder in the open [Agent Skills](https://agentskills.io/) format. `steering/` holds process: the EKS hub routes your request to a workflow (design, build, upgrade check, operational review), and the workflow loads the skills it needs. Slash commands like `/apex:eks` and `/apex:eks-design` are the doors in.

That line works, and we are keeping it. But two things were missing. There was no single front door, and there was no obvious place for a customer to say "this is how *we* run an upgrade".

## One hub, many children

The new design has two kinds of skill. A **hub** skill, `apex`, is the entry point: it knows the engagements APEX can run and holds the runbooks that drive them. **Child** skills, such as `eks-design`, `eks-build` and `eks-upgrade-check`, hold the domain knowledge. A runbook in the hub loads the children it needs, step by step.

And `/apex` becomes the front door. Today `apex` is only the prefix on commands like `/apex:eks`; there is no bare `/apex`, and nothing takes you straight to the APEX entry point. In the new design, `/apex` routes directly into the apex skill.

We have not settled what to call this shape, and we want to get it right, because the name is how everyone will talk about it. **Hub and children** matches the "central hub" language the repo already uses, but mixes metaphors. **Hub and spoke** is one clean metaphor that many readers know, but it suggests children only connect through the hub, and the term already means a cluster topology in our platform engineering skill. **Parent and child** reads naturally ("the parent loads the child") but hints at inheritance, and skills do not inherit anything. We will pick one with the maintainers and record it as a decision.

## Day 0, Day 1, Day 2

Our workflows already carry a lifecycle tag. The common reading: **Day 0** is design and planning, **Day 1** is build and deploy, **Day 2** is everything after go-live, such as upgrades, reviews and security posture.

That gives us a few rules of thumb. A child skill usually serves one stage well. A runbook often crosses stages, because a design hands over to a build and a review feeds the next design, so chaining is the hub's job, not a skill's. And Day 2 is where customization pays most: Day 0 and Day 1 follow fairly standard steps, while Day 2 depends on your change process, your tooling and your on-call model.

## Where do runbooks live?

A runbook is the step-by-step part of an engagement: what to ask, in what order, which skill to load, what to hand back.

Our first answer was: inside each skill, for example `eks-design/runbook/`. The reason was standalone use. Pick up one folder and you have everything.

Then we looked at the catalog growing sideways. Say we have `eks-design` and `gke-design`. Two runbook folders with near-identical steps, drifting apart over time. One runbook in `apex/runbooks/` could guide both.

A maintainer pushed the argument further, and it won us over: give customers **one entry point**, and let them use, update and edit **every runbook in one place**. So that is the decision. Runbooks live in `apex/runbooks/`, and they come out of the other skills.

## The runbook is the part you change

This is the idea that ties it together. The rest of a skill is domain knowledge: facts, decision frameworks, references. That should stay close to upstream, because it gets better every time we update it. The runbook is different. It is where APEX meets *your* way of working: your approval gates, your naming, your tooling. We strongly advise customizing it.

We are not enforcing that split with folder tricks. Instead, the design notes explain the decisions we made, so you can read them, understand them, and adapt or change them as you like. With every runbook in one folder, you have one place to fork, review and carry across upgrades.

## The trade-off we accept

There is a cost. A child skill still works on its own in any agent that reads the Agent Skills format, but without the hub it has no runbook. You get the knowledge, not the guided engagement. We accept that: if you do not take the full APEX setup, you get a weaker product, and we would rather say so plainly than copy runbooks into every skill.

## What comes next

None of this is built yet: there is no apex skill, no `apex/runbooks/` folder and no bare `/apex` command today. These notes describe where we are heading for the next major version, and they will fold into its release docs when it ships. Later posts will cover how we engineer the harness around the skills and how we evaluate them.

The decisions so far, in the repo:

- [ADR 0001: Runbooks live in one place under the apex skill](https://github.com/aws-samples/sample-apex-skills/blob/main/docs/adr/0001-runbooks-live-in-apex.md)
- [ADR 0002: `/apex` routes directly into the apex skill](https://github.com/aws-samples/sample-apex-skills/blob/main/docs/adr/0002-apex-command-routes-to-apex-skill.md)
- [ADR 0003: A standalone skill is an accepted, weaker trade-off](https://github.com/aws-samples/sample-apex-skills/blob/main/docs/adr/0003-standalone-skills-are-a-weaker-tradeoff.md)
- [The skill design notes](https://github.com/aws-samples/sample-apex-skills/blob/main/docs/design/skill-design.md)
