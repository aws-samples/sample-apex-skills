---
name: apex:<workflow-name>
description: <One sentence mirroring the workflow description, one notch more action-oriented. Front-load the lifecycle phase and the concrete verbs users will type.>
---
<objective>
Run the APEX <workflow-name> workflow — <one sentence: what running this command accomplishes for the user>.
</objective>

<execution_context>
@~/.claude/apex-steering/workflows/<workflow-name>.md
</execution_context>

<process>
Follow the <workflow-name> workflow end-to-end. Detect the user's mode from their message and route into the matching row of the workflow's "How to Route Requests" table. Use the <primary-knowledge-skill> skill for decision frameworks and reference material. Phases: 1) <gather context>, 2) <inspect current state>, 3) <frame the decision>.
</process>
