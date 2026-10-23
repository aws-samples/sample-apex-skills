# Architecture Decision Records

Each record captures one decision: the context, what we decided, and what follows from it. Records are short and numbered in the order we made them. A record is not edited to change its decision; a later record supersedes it.

| ADR | Title | Status |
|-----|-------|--------|
| [0001](0001-runbooks-live-in-apex.md) | Runbooks live in one place under the apex skill | Accepted |
| [0002](0002-apex-command-routes-to-apex-skill.md) | `/apex` routes directly into the apex skill | Accepted |
| [0003](0003-standalone-skills-are-a-weaker-tradeoff.md) | A standalone skill is an accepted, weaker trade-off | Accepted |
| [0004](0004-naming.md) | One entry skill, and standalone knowledge and solution skills | Accepted |

## Format

Each record has these sections:

- **Status**: Proposed, Accepted, or Superseded by a later ADR.
- **Date**: the day the decision was made.
- **Context**: the problem and the forces behind it, including the options we did not take.
- **Decision**: what we chose, in one or two paragraphs.
- **Consequences**: what gets easier, what gets harder, and what has to change in the repo.

The wider reasoning lives in the [skill design notes](../design/skill-design.md).
