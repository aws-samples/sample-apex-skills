# Advisor rules

An Advisor skill gives knowledge and guidance; it does not do the task.

- **advisor.no-side-effects**: Make no change to the user's account, cluster or files, even when the user confirms one: this class removes the confirm-and-change path `apex.read-only-unless-confirmed` allows. A change belongs to an Operator skill. Example commands in `references/` that change a cluster or account stay for the customer: each is marked customer-run, and you never run one.
