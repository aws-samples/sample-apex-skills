---
name: apex:eks-upgrade
description: Plan and execute an EKS cluster upgrade. Pre-flight validation, Terraform or CLI path detection, step-by-step execution with checkpoints, and post-upgrade validation. Supports in-place and blue-green strategies.
---
<objective>
Run the APEX EKS upgrade workflow -- structured pre-flight checks, upgrade planning, execution with rollback awareness, and validation.
</objective>

<execution_context>
@~/.claude/apex-steering/workflows/upgrade.md
</execution_context>

<process>
Follow the upgrade workflow end-to-end. Detect the user's mode (full upgrade, assessment, pre-flight, scoped, or rollback advisory) and route accordingly. Use the eks-upgrader skill for upgrade procedures, pre-flight checks, and rollback guidance. Use eks-best-practices for Terraform examples and general architecture context.
</process>
