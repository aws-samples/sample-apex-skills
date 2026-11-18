# Advisor rules

An Advisor skill gives knowledge and guidance; it does not do the task.

- **advisor.no-side-effects**: Change nothing on your own. A change to the user's account, cluster or files follows `apex.read-only-unless-confirmed`, the same as in every APEX skill: only when the user explicitly asks for it, after you show the exact command and what it changes and the user says yes. Example commands in `references/` that change a cluster or account stay for the customer, each marked customer-run, and run only on that explicit ask.
