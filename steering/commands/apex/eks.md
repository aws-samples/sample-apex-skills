---
name: apex:eks
description: EKS platform engineering hub. Routes to design or upgrade workflows based on your request. Use for any EKS-related task -- architecture design, cluster upgrades, reviews, comparisons, or general EKS questions.
---
<objective>
Route the user's EKS request to the appropriate workflow using the APEX EKS steering hub.
</objective>

<execution_context>
@steering/eks.md
</execution_context>

<process>
Read the steering hub and follow its routing logic. Detect the user's intent from their message and route to the appropriate workflow (design or upgrade). If the request doesn't match a workflow, use the eks-best-practices skill directly.
</process>
