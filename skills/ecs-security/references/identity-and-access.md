# Layer 2 — Identity & Access on ECS

This is the highest-value layer for ECS because the **#1 recurring hard question** in the field is a role-trust misconfiguration: *"ECS was unable to assume the role."* Two concerns compound: **which role does what**, and **how to make each trust policy least-privilege and confused-deputy-safe**.

## The four ECS roles — get them distinct

ECS uses several IAM roles for different jobs. Conflating them is the classic misconfiguration. Reference: [Best practices for IAM roles in Amazon ECS](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/security-iam-roles.html).

| Role | Who uses it | For what | When required |
|---|---|---|---|
| **Task role** | Your **application code** inside the container | Calls to other AWS services (S3, DynamoDB, …) at **runtime** | When the app accesses AWS services |
| **Task execution role** | The **ECS/Fargate agent**, not your code | Pull images from ECR, write logs (`awslogs`), **fetch Secrets Manager/SSM secrets at launch**, Runtime Monitoring, private-registry auth | **Fargate, ECS Managed Instances, or external instances** for ECR-private + `awslogs`; **Fargate or EC2** for secrets/private-registry/Runtime Monitoring (verified — [task execution role](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_execution_IAM_role.html)) |
| **Container instance role** | The **EC2 instance** (EC2 launch type) | Register the instance with the cluster, agent → ECS API | ECS on EC2 / external instances |
| **Infrastructure role** | ECS itself | Manage EBS volume attach, Service Connect TLS, VPC Lattice target groups on your behalf | When using those features |

> **The single most important distinction (verified):** the **execution role** grants the *agent* permission to prepare and launch the task (pull image, write logs, retrieve secrets). The **task role** vends temporary credentials to *your application code at runtime* via the container credentials endpoint (`AWS_CONTAINER_CREDENTIALS_RELATIVE_URI` → `169.254.170.2`). Putting your app's S3 permissions on the execution role, or putting ECR/secrets-retrieval permissions only on the task role, is the classic error. Sources: [task execution role](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_execution_IAM_role.html) · [task role](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-iam-roles.html).

- Use the AWS managed **`AmazonECSTaskExecutionRolePolicy`** as the execution-role baseline, then add inline permissions for the specific secrets ARNs the task reads. Do **not** overload it.
- **One task role per task definition/service**, least-privileged — AWS explicitly recommends a distinct role per task definition with only the permissions that task needs, rather than a shared role.
- Task-role credentials are, **by default, valid for six hours** and auto-rotated by the agent; app code doesn't manage renewal (modern SDKs fetch from the credentials endpoint automatically). Verified 2026-07-09: *"By default, credentials assigned to tasks using task roles are valid for six hours"* ([Best practices for IAM roles in Amazon ECS](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/security-iam-roles.html)).

## Trust policy — the `ecs-tasks.amazonaws.com` principal

Both the task role and the execution role must trust the ECS tasks service. The minimal trust policy is:

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": { "Service": "ecs-tasks.amazonaws.com" },
    "Action": "sts:AssumeRole"
  }]
}
```

## Confused-deputy protection (add `aws:SourceArn` + `aws:SourceAccount`)

Because `ecs-tasks.amazonaws.com` is a shared AWS service principal, harden the trust policy against the **confused-deputy problem** — so the ECS service can only assume the role *on behalf of your account's tasks*, not another customer's. Scope with `aws:SourceAccount` (your account) and `aws:SourceArn`. The exact form AWS documents (verified 2026-07-09 against [ECS task IAM role](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-iam-roles.html)) uses an **all-clusters wildcard** `arn:aws:ecs:region:account:*`:

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": { "Service": "ecs-tasks.amazonaws.com" },
    "Action": "sts:AssumeRole",
    "Condition": {
      "StringEquals": { "aws:SourceAccount": "111122223333" },
      "ArnLike": { "aws:SourceArn": "arn:aws:ecs:region:111122223333:*" }
    }
  }]
}
```

> **Gotcha (corrected):** you **cannot** scope this `aws:SourceArn` to a specific cluster or task-family. AWS states verbatim: *"Using the `aws:SourceArn` condition key to specify a specific cluster is not currently supported, you should use the wildcard to specify all clusters"* — so the account-scoped `...:account:*` above is the tightest supported form. A task-family SourceArn is impossible in principle: a task ARN is `arn:aws:ecs:region:account:task/cluster-name/task-id` and never contains the family. Attempting a narrower pattern is the classic self-inflicted "unable to assume the role." Source: [ECS task IAM role](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-iam-roles.html) · [AWS confused-deputy prevention](https://docs.aws.amazon.com/IAM/latest/UserGuide/confused-deputy.html).

## `iam:PassRole` — scope it, never `*`

Whoever registers a task definition or creates a service (a CI/CD pipeline, CodeDeploy, EventBridge scheduler, a developer) must have **`iam:PassRole`** for the task role and execution role being attached — this is how AWS prevents privilege escalation via role attachment. Scope it to the exact role ARNs:

```json
{
  "Effect": "Allow",
  "Action": "iam:PassRole",
  "Resource": [
    "arn:aws:iam::111122223333:role/myAppTaskRole",
    "arn:aws:iam::111122223333:role/ecsTaskExecutionRole"
  ],
  "Condition": { "StringEquals": { "iam:PassedToService": "ecs-tasks.amazonaws.com" } }
}
```

Never grant `iam:PassRole` on `Resource: "*"` — that lets the principal attach *any* role (including an admin role) to a task; over-broad `iam:PassRole` is a well-known container privilege-escalation path. (Separately, AWS has **deprecated/phased out** several broad ECS managed policies such as `AmazonEC2ContainerServiceFullAccess` and `AmazonEC2ContainerServiceRole` in favor of scoped policies and service-linked roles — stated here as a deprecation, not a documented causal link. See [Phased-out AWS managed IAM policies for ECS](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/security-iam-awsmanpol-deprecated-policies.html).) CodeDeploy, EventBridge, and CI runners each need their own scoped `iam:PassRole` — see [CodeDeploy IAM role](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/codedeploy_IAM_role.html), [EventBridge IAM role](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/CWE_IAM_role.html), [infrastructure role pass permission](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/infrastructure_IAM_role.html).

## Diagnosing "ECS was unable to assume the role"

This is the recurring firefight. Work the checklist in order (per [re:Post: ECS unable to assume role](https://repost.aws/knowledge-center/ecs-unable-to-assume-role)):
1. **Does the role exist?** `aws iam get-role --role-name <role>` — a deleted/renamed/typo'd role ARN in the task definition is the most common cause.
2. **Trust policy correct?** It must allow `sts:AssumeRole` for `Principal.Service = ecs-tasks.amazonaws.com`. A trust policy pointing at `ec2.amazonaws.com` (copied from an instance profile) is a frequent mistake.
3. **Confused-deputy condition too tight?** An `aws:SourceArn`/`aws:SourceAccount` condition that doesn't match the actual account will deny the assume. Widen `aws:SourceArn` to the documented all-clusters wildcard `arn:aws:ecs:region:account:*` (cluster/task-family scoping is unsupported — see above) and confirm `aws:SourceAccount` is the launching account.
4. **Right role in the right field?** Confirm the execution role is in `executionRoleArn` and the task role in `taskRoleArn` — swapping them causes launch-time failures (agent can't pull/log) or runtime failures (app can't call AWS).
5. **`iam:PassRole` present** for the principal creating the service/registering the task def.
6. **Self-assume edge case:** if a task's role must assume *itself*, the trust policy must explicitly allow that (per [Updating a role trust policy](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_update-role-trust-policy.html)).

## ECS Exec governance (the biggest under-controlled surface)

**ECS Exec** (`aws ecs execute-command`) opens an interactive shell into a running container. It is invaluable for break-glass debugging and a serious lateral-movement risk if ungoverned — and note two verified facts (2026-07-09, [ECS Exec](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-exec.html)): **Exec commands always run as `root`** ("these commands are run as the `root` user … even when you specify a user ID for the container"), and **`readonlyRootFilesystem: true` is not supported with Exec** (the SSM agent must write to the container FS). Govern it explicitly:

- **Restrict who can Exec, and into what** — scope `ecs:ExecuteCommand` in the caller's IAM policy with condition keys: `ecs:cluster` (which clusters), `ecs:container-name` (which containers), and resource tags on the cluster/task. AWS shows these exact patterns under [Using IAM policies to limit access to ECS Exec](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-exec.html). Also consider limiting the underlying `ssm:StartSession`.
- **Log every session** — set the cluster `configuration.executeCommandConfiguration` to log sessions to **CloudWatch Logs and/or S3** (`logging: OVERRIDE`), and encrypt the session with a **KMS key** (`kmsKeyId`). When using a KMS key you must also add a KMS interface VPC endpoint on private networks.
- **Audit** — `ExecuteCommand` is a CloudTrail event; alert on it. Session command/output logs give you the in-container audit trail.
- **Disable in production** — the task must opt in via `enableExecuteCommand`; leave it **off** for prod services unless a break-glass workflow is active, and pair the task-role SSM permissions (`ssmmessages:*`) with the IAM restrictions above.

## Operator-side IAM (cluster administration, not just workload roles)

Layers above cover the *workload* roles; the *operators* who manage ECS need least-privilege too (per [ECS security IAM best practices](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/security-iam-roles.html) and the [ECS security best-practices guide](https://docs.aws.amazon.com/AmazonECS/latest/bestpracticesguide/security-iam.html)):

- **Treat the cluster as an administrative boundary** and split operator personas — e.g. an `AdminRole` that can `CreateCluster`/`DeleteCluster`/`UpdateService` vs a `DeveloperRole` scoped to deploy within named clusters.
- **ABAC** — tag clusters/services and gate operator actions on matching principal/resource tags to scale least-privilege without per-resource policies.
- **MFA conditions** (`aws:MultiFactorAuthPresent`) on destructive ECS actions, and scope `iam:PassRole` (above) so operators can only pass the intended task/execution/infrastructure roles.

## Cross-account access

A task role can assume a role in another account for cross-account resource access — the target account's role trusts the task role's ARN, and the task role holds `sts:AssumeRole` for it. Add confused-deputy conditions on the target trust policy too. For CloudTrail auditability, task credentials carry a `taskArn` session context so you can trace which task made a call ([task role auditability](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-iam-roles.html)).

## Shared responsibility (Layer 2)

| AWS manages | Customer manages |
|---|---|
| The `ecs-tasks.amazonaws.com` assume plane; credential vending to the container endpoint; default six-hour auto-rotation; CloudTrail recording; ECS Exec session transport (SSM) | Role split (task vs execution vs instance vs infra); least-privilege policies; trust-policy correctness + confused-deputy conditions; scoped `iam:PassRole`; cross-account trust; ECS Exec IAM restrictions + session logging/encryption; operator-role least-privilege |

## Sources
- [Best practices for IAM roles in Amazon ECS](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/security-iam-roles.html) · [ECS task IAM role](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-iam-roles.html) · [ECS task execution IAM role](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_execution_IAM_role.html)
- [re:Post — "ECS was unable to assume the role"](https://repost.aws/knowledge-center/ecs-unable-to-assume-role) · [AWS confused-deputy prevention](https://docs.aws.amazon.com/IAM/latest/UserGuide/confused-deputy.html) · [Updating a role trust policy](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_update-role-trust-policy.html)
- [CodeDeploy IAM role](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/codedeploy_IAM_role.html) · [EventBridge IAM role](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/CWE_IAM_role.html) · [Infrastructure role pass permission](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/infrastructure_IAM_role.html)
- [Monitor Amazon ECS containers with ECS Exec](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-exec.html) · [Phased-out AWS managed IAM policies for ECS](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/security-iam-awsmanpol-deprecated-policies.html)
