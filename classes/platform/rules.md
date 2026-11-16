# Platform rules

Platform holds what Advisor and Operator skills share: how a skill's guidance is read and checked before it reaches the user. It sits under APEX Skills and above Advisor and Operator.

- **platform.reading-hint**: The essentials are in SKILL.md; load a reference only when the task needs that depth.
- **platform.advisory-sections**: Where the skill has a `## Security Baseline (non-negotiable)` section, every recommendation includes it. Where it has a `## Top Guardrails (the high-cost mistakes)` section, check each recommendation against it before you give it.
