---
name: apex:eks-design
description: Design a new EKS cluster architecture. 8-phase questionnaire covering compute, networking, security, observability, cost, reliability, and multi-tenancy. Also handles architecture reviews and option comparisons.
---
<objective>
Run the APEX EKS design workflow -- a structured questionnaire that gathers requirements and generates architecture recommendations.
</objective>

<execution_context>
@~/.claude/apex-steering/workflows/design.md
</execution_context>

<process>
Follow the design workflow end-to-end. Use the eks-best-practices skill for decision frameworks and reference material. Detect the user's intent (new design, scoped design, review, or comparison) and route accordingly within the workflow.
</process>
