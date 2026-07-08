---
title: "Layer 2 — Identity & Access on ECS"
description: ""
custom_edit_url: https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-security/references/identity-and-access.md
format: md
---

:::info[Source]
This page is generated from [skills/ecs-security/references/identity-and-access.md](https://github.com/aws-samples/sample-apex-skills/blob/main/skills/ecs-security/references/identity-and-access.md). Edit the source, not this page.
:::

# Layer 2 — Identity & Access on ECS

This is the highest-value layer for ECS because the **#1 recurring hard question** in the field is a role-trust misconfiguration: *"ECS was unable to assume the role."* Two concerns compound: **which role does what**, and **how to make each trust policy least-privilege and confused-deputy-safe**.

## The four ECS roles — get them distinct

ECS uses several IAM roles for different jobs. Conflating them is the classic misconfiguration. Reference: [Best practices for IAM roles in Amazon ECS](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/security-iam-roles.html).

| Role | Who uses it | For what | When required |
|---|---|---|---|
| **Task role** | Your **application code** inside the container | Calls to other AWS services (S3, DynamoDB, …) at **runtime** | When the app accesses AWS services |
| **Task execution role** | The **ECS/Fargate agent**, not your code | Pull images from ECR, write logs (`awslogs`), **fetch Secrets Manager/SSM secrets at launch**, Runtime Monitoring, private-registry auth | Fargate/external always for ECR-private + logs; any launch type for secrets/private-registry/Runtime Monitoring |
| **Container instance role** | The **EC2 instance** (EC2 launch type) | Register the instance with the cluster, agent → ECS API | ECS on EC2 / external instances |
| **Infrastructure role** | ECS itself | Manage EBS volume attach, Service Connect TLS, VPC Lattice target groups on your behalf | When using those features |

> **The single most important distinction (verified):** the **execution role** grants the *agent* permission to prepare and launch the task (pull image, write logs, retrieve secrets). The **task role** vends temporary credentials to *your application code at runtime* via the container credentials endpoint (`AWS_CONTAINER_CREDENTIALS_RELATIVE_URI` → `169.254.170.2`). Putting your app's S3 permissions on the execution role, or putting ECR/secrets-retrieval permissions only on the task role, is the classic error. Sources: [task execution role](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_execution_IAM_role.html) · [task role](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-iam-roles.html).

- Use the AWS managed **`AmazonECSTaskExecutionRolePolicy`** as the execution-role baseline, then add inline permissions for the specific secrets ARNs the task reads. Do **not** overload it.
- **One task role per task definition/service**, least-privileged — AWS explicitly recommends a distinct role per task definition with only the permissions that task needs, rather than a shared role.
- Task-role credentials are valid for ~6 hours and auto-rotated by the agent; app code doesn't manage renewal (modern SDKs fetch from the credentials endpoint automatically).

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

Because `ecs-tasks.amazonaws.com` is a shared AWS service principal, harden the trust policy against the **confused-deputy problem** — so the ECS service can only assume the role *on behalf of your account's tasks*, not another customer's. Scope with `aws:SourceAccount` (your account) and `aws:SourceArn` (the task ARN pattern). This mirrors AWS's cross-service confused-deputy guidance:

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": { "Service": "ecs-tasks.amazonaws.com" },
    "Action": "sts:AssumeRole",
    "Condition": {
      "StringEquals": { "aws:SourceAccount": "111122223333" },
      "ArnLike": { "aws:SourceArn": "arn:aws:ecs:region:111122223333:task/*" }
    }
  }]
}
```

> **Gotcha:** an over-restrictive `aws:SourceArn` (e.g. pinned to a single task ID that no longer exists) will itself cause "unable to assume the role." Scope to a cluster/task-family pattern, not a one-shot ARN. General reference for the pattern: [AWS confused-deputy prevention](https://docs.aws.amazon.com/IAM/latest/UserGuide/confused-deputy.html).

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

Never grant `iam:PassRole` on `Resource: "*"` — that lets the principal attach *any* role (including an admin role) to a task. The blast radius of over-broad `iam:PassRole` is exactly why AWS phased out `AmazonEC2ContainerServiceFullAccess`. CodeDeploy, EventBridge, and CI runners each need their own scoped `iam:PassRole` — see [CodeDeploy IAM role](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/codedeploy_IAM_role.html), [EventBridge IAM role](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/CWE_IAM_role.html), [infrastructure role pass permission](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/infrastructure_IAM_role.html).

## Diagnosing "ECS was unable to assume the role"

This is the recurring firefight. Work the checklist in order (per [re:Post: ECS unable to assume role](https://repost.aws/knowledge-center/ecs-unable-to-assume-role)):
1. **Does the role exist?** `aws iam get-role --role-name <role>` — a deleted/renamed/typo'd role ARN in the task definition is the most common cause.
2. **Trust policy correct?** It must allow `sts:AssumeRole` for `Principal.Service = ecs-tasks.amazonaws.com`. A trust policy pointing at `ec2.amazonaws.com` (copied from an instance profile) is a frequent mistake.
3. **Confused-deputy condition too tight?** An `aws:SourceArn`/`aws:SourceAccount` condition that doesn't match the actual task/account will deny the assume. Widen to a cluster/family pattern.
4. **Right role in the right field?** Confirm the execution role is in `executionRoleArn` and the task role in `taskRoleArn` — swapping them causes launch-time failures (agent can't pull/log) or runtime failures (app can't call AWS).
5. **`iam:PassRole` present** for the principal creating the service/registering the task def.
6. **Self-assume edge case:** if a task's role must assume *itself*, the trust policy must explicitly allow that (per [Updating a role trust policy](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_update-role-trust-policy.html)).

## Cross-account access

A task role can assume a role in another account for cross-account resource access — the target account's role trusts the task role's ARN, and the task role holds `sts:AssumeRole` for it. Add confused-deputy conditions on the target trust policy too. For CloudTrail auditability, task credentials carry a `taskArn` session context so you can trace which task made a call ([task role auditability](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-iam-roles.html)).

## Shared responsibility (Layer 2)

| AWS manages | Customer manages |
|---|---|
| The `ecs-tasks.amazonaws.com` assume plane; credential vending to the container endpoint; ~6h auto-rotation; CloudTrail recording | Role split (task vs execution vs instance vs infra); least-privilege policies; trust-policy correctness + confused-deputy conditions; scoped `iam:PassRole`; cross-account trust |

## Sources
- [Best practices for IAM roles in Amazon ECS](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/security-iam-roles.html) · [ECS task IAM role](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-iam-roles.html) · [ECS task execution IAM role](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_execution_IAM_role.html)
- [re:Post — "ECS was unable to assume the role"](https://repost.aws/knowledge-center/ecs-unable-to-assume-role) · [AWS confused-deputy prevention](https://docs.aws.amazon.com/IAM/latest/UserGuide/confused-deputy.html) · [Updating a role trust policy](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_update-role-trust-policy.html)
- [CodeDeploy IAM role](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/codedeploy_IAM_role.html) · [EventBridge IAM role](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/CWE_IAM_role.html) · [Infrastructure role pass permission](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/infrastructure_IAM_role.html)
