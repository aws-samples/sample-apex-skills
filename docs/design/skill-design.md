# APEX skill design

> Status: working notes, 2026-10-23. This describes the target design for the next major version of APEX. Parts of it are decided (see the [ADRs](../adr/README.md)); parts are still open and marked as such. Where the repo works differently today, we say so.

This document is about how we design skills: how they fit together, how the lifecycle of a platform shapes them, and where the customizable parts live. We are starting simple. Over time it will grow to cover how we test and evaluate skills and the harness around them.

## Where we are today

The repo splits knowledge from process:

- `skills/` holds domain knowledge. Each skill is a self-contained folder (`SKILL.md` plus references and scripts) in the open [Agent Skills](https://agentskills.io/) format.
- `steering/` holds process. The EKS hub `steering/eks.md` routes a request to a workflow in `steering/workflows/` (design, build, upgrade check, operational review and others), and each workflow loads the skills it needs. The slash commands in `steering/commands/apex/` (`/apex:eks`, `/apex:eks-design` and so on) are thin entry points into those steering files.

That split works. What it lacks is one entry point and one place where a customer adapts the process to their own way of working. The rest of this document is about closing those two gaps.

## The hub and children model

The new design has two kinds of skill:

- **A hub skill** is the entry point. It knows the engagements APEX can run, asks enough to pick the right one, and holds the runbooks that drive them. `apex` is the hub, and `/apex` takes you straight to it ([ADR 0002](../adr/0002-apex-command-routes-to-apex-skill.md)).
- **Child skills** hold domain knowledge: `eks-design`, `eks-build`, `eks-upgrade-check` and the rest. A runbook in the hub loads the children it needs, step by step.

### What to call it: open

We have not settled the name. It matters, because the name is how contributors and customers will talk about the structure, so we want to think it through properly before we pick. This is to be decided with the maintainers. The options so far:

| Name | For | Against |
|------|-----|---------|
| **Hub and children** | "Hub" already appears in the repo (`steering/eks.md` calls itself the central hub). "Children" says the child skills belong to a family. | Mixes two metaphors (a wheel and a family tree). |
| **Hub and spoke** | One consistent metaphor. Widely understood in networking and architecture, so many readers know it already. | Spokes suggest the children only connect through the hub. In practice a child skill can also be used on its own, and one child can call another. The term is also already used in the EKS platform engineering skill for a cluster topology, which could confuse readers. |
| **Parent and child** | Familiar from software (parent and child processes, components). Reads naturally in docs: "the parent skill loads the child skill". | Suggests inheritance: that children get behavior or settings from the parent. Skills do not inherit anything; the hub routes and orchestrates. |

Whatever we pick, we will use it everywhere, in docs, skill frontmatter and folder names, and record it as an ADR.

## Day 0, Day 1, Day 2

> Draft: for the maintainers to confirm.

The repo already tags workflows by lifecycle: the routing table in `steering/eks.md` has a Lifecycle column, and each workflow names its stage. The common reading of the three stages:

- **Day 0: design and planning.** Requirements, architecture, option comparisons, design reviews. The output is a decision and a document, not running infrastructure. Today: the design workflow and `eks-design`.
- **Day 1: build and deploy.** Turning the design into code and infrastructure, and getting the first workloads running. Today: the build, platform engineering and GenAI workflows.
- **Day 2: operate.** Everything after go-live: upgrades, operational and cost reviews, security posture, migrations. Today: the upgrade check, operational review and ingress migration skills.

How this shapes the design:

- **Skills follow the lifecycle.** A child skill usually serves one stage well. Naming the stage in the skill's own description helps the hub route to it and helps a reader know what to expect.
- **Runbooks span the lifecycle.** An engagement often crosses stages: a design hands over to a build, and an operational review feeds the next design. A runbook in the hub can chain children across stages, which a single skill should not try to do.
- **Day 2 is where customization pays most.** Day 0 and Day 1 follow fairly standard steps. Day 2 depends on the customer's own change process, tooling, approvals and on-call model, so Day 2 runbooks are the ones customers will adapt most.

## Runbooks

A runbook is the step-by-step part of an engagement: what to ask, in what order, which skill to load at each step, and what to hand back.

### Where they live

We looked at two places.

**In each skill**, for example `eks-design/runbook/`. This was our first choice. The appeal is standalone use: a user picks up one skill folder and has everything, runbook included.

**In one place under the hub**, for example `apex/runbooks/`. The appeal is reach and a single place to work. Say we have `eks-design` and `gke-design`: instead of two runbook folders with near-identical steps, one runbook in apex guides both. A maintainer made the stronger case: customers get one entry point, and can use, update and edit every runbook in one place.

**Decision:** runbooks live in `apex/runbooks/`, and we remove runbooks from the other skills. See [ADR 0001](../adr/0001-runbooks-live-in-apex.md).

### How customers adapt them

This is the idea going forward: the rest of a skill is domain knowledge, and the runbook is the customizable part.

- **Domain knowledge** (the child skills) should stay close to upstream. It is facts, decision frameworks and references, and it improves when we update it.
- **Runbooks** are where a customer fits APEX to their own use case: their approval gates, their naming, their tooling, the order they like to work in. We strongly advise customers to customize them.

We do not enforce this in the repo layout. Instead this document is where we explain the decisions we made, so readers can understand them and adapt or change them as they like. Keeping every runbook in `apex/runbooks/` means a customer has one folder to fork, review and carry across upgrades.

### Standalone skills

A child skill still works on its own, in any agent that reads the Agent Skills format. But without the hub it has no runbook, so you get the knowledge without the guided engagement. We accept that as a design trade-off: users who do not take the full APEX setup get a weaker product. See [ADR 0003](../adr/0003-standalone-skills-are-a-weaker-tradeoff.md).

## What comes later

These notes cover the shape of a skill. Later versions of this document will add how we engineer the harness around the skills and how we evaluate them.

The repo does not match this design yet: there is no apex skill, no `apex/runbooks/` folder and no bare `/apex` command today. These notes fold into the release documentation when the next major version ships. Until then, this is where we record the decisions as we make them.
