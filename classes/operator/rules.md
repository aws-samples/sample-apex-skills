# Operator rules

An Operator skill does a task for the user.

- **operator.confirm-before-change**: Before any change to the user's account, cluster or files, show what will change and wait for the user's explicit confirmation, as `apex.read-only-unless-confirmed` says (the exact command and what it changes).
- **operator.typed-input**: Take the task's input in the shape the skill declares, and check it before you start.
- **operator.artifact-checks**: A skill that produces an artifact declares that artifact's checks in its frontmatter, `metadata.apex-artifact-checks` (a list of check ids), and the artifact must pass them before you hand it over.
