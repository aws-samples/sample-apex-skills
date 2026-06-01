---
name: apex:eks-build
description: Build a production-ready EKS cluster. Multi-phase questionnaire gathering requirements then generating Terraform code via the eks-build skill.
---
<objective>
Run the APEX EKS build workflow — a structured questionnaire that gathers requirements and generates production-ready Terraform code.
</objective>

<execution_context>
@~/.claude/apex-steering/workflows/eks-build.md
</execution_context>

<process>
Follow the build workflow end-to-end. Use the eks-build skill for code generation and the eks-best-practices skill for decision frameworks. Detect the user's intent (new build, resume existing, modify, pattern selection) and route accordingly within the workflow.
</process>
