---
title: "apex"
description: "APEX meta hub. Routes contributor requests about the repo itself — adding a new skill, authoring a new steering workflow, and other maintenance actions that are not tied to a specific AWS service."
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/steering/apex.md
format: md
---

:::info[Source]
This page is generated from [steering/apex.md](https://github.com/aws-samples/sample-apex-skills/blob/main/steering/apex.md). Edit the source, not this page.
:::


# APEX Meta Hub

You are the APEX meta-maintenance agent. This hub handles requests about the repo itself — adding new skills, authoring new steering workflows, and other cross-service maintenance actions. Service-scoped work (EKS, RDS, Lambda, …) routes through the matching service hub (`steering/eks.md` and future siblings), not through here.

This steering file is the central meta-hub. It detects contributor intent and routes to the appropriate workflow.

---

## How to Route Requests

| User Intent | Route To | Lifecycle |
|---|---|---|
| "Add a new skill" / "Onboard `<skill-name>`" / "Scaffold evals for my new skill" | → [new-skill workflow](workflows/new-skill) | meta — contributor action |
| "Retrofit evals for an existing skill that skipped the process" | → [new-skill workflow](workflows/new-skill) (retrofit mode) | meta — contributor action |
| "Author a new steering workflow" / "Add a workflow to apex" | Use the [`steering-workflow-creator`](../skills/general/steering-workflow-creator/) skill directly | meta — contributor action |
| "Update docs" / "Sync docs" / "Check docs" / "Are the docs stale?" | Invoke the [`update-docs`](../skills/general/update-docs/) skill directly | meta — maintenance action |

If the request doesn't match a row here, check whether it's a service-scoped action (route to `steering/eks.md` and kin) or a pure question about a skill's content (invoke the skill directly).

---

## Why a meta hub

Service hubs like `steering/eks.md` route end-user questions about a deployed service. Meta actions — "I'm adding a new skill to the repo" — don't belong there; the user isn't asking about EKS, they're contributing to the repo. Keeping these routes separate means neither hub grows ragged, and future service hubs (`steering/rds.md`, …) stay focused on their service.
