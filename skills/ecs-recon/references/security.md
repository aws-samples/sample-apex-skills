# Module: Security

> **Part of:** [ecs-recon](../SKILL.md)
> **Purpose:** Discover security-relevant configuration including IAM roles, secrets references, and ECS Exec enablement for ECS services

## Table of Contents

- [Prerequisites](#prerequisites)
- [Detection Strategy](#detection-strategy)
- [Detection Commands](#detection-commands)
  - [Task Role and Execution Role](#1-task-role-and-execution-role)
  - [Secrets References](#2-secrets-references)
  - [ECS Exec Enablement](#3-ecs-exec-enablement)
- [Output Schema](#output-schema)
- [Edge Cases](#edge-cases)

---

## Prerequisites

- **Service name(s) required:** Yes (one or more services to inspect)
- **Active task definition required:** Yes (resolved from service's `taskDefinition` field)
- **AWS APIs used:**
  - `ecs:DescribeTaskDefinition` — task role, execution role, container secrets
  - `ecs:DescribeServices` — ECS Exec enablement (`enableExecuteCommand` field)
- **CLI commands:** `aws ecs describe-task-definition`, `aws ecs describe-services`
- **IAM permissions:** Read-only (`ecs:DescribeTaskDefinition`, `ecs:DescribeServices`)

---

## Detection Strategy

Run detections in this order to build the security posture from identity down to debug access:

```
1. Task Role + Execution Role  -> Extract IAM role ARNs from the active task definition
2. Secrets References          -> Enumerate secrets injected into containers from the task definition
3. ECS Exec Enablement         -> Check if interactive exec is enabled on the service
```

**Why this order matters:**
- IAM roles define the identity and permission boundary — the most critical security attribute
- Secrets references reveal what sensitive data is injected and from which stores (Secrets Manager vs SSM Parameter Store)
- ECS Exec enablement indicates debug access posture — the last piece of the security picture

**Key concepts:**
- **Task role** (`taskRoleArn`): The IAM role that containers in the task assume at runtime to interact with AWS services. This is the identity your application code uses.
- **Execution role** (`executionRoleArn`): The IAM role the ECS agent uses on behalf of the task — it pulls container images from ECR, publishes logs to CloudWatch, and retrieves secrets.
- **Secrets**: Container definitions reference secrets by ARN or parameter name. ECS resolves these at task launch and injects them as environment variables.
- **ECS Exec**: When enabled on a service, operators can exec into running containers for debugging. Requires both the service-level `enableExecuteCommand` flag and appropriate IAM permissions.

---

## Detection Commands

### 1. Task Role and Execution Role

Retrieve the task definition to extract the IAM roles. The active task definition ARN is obtained from the service (via `describe-services`), then described for full details.

**Step 1 — Get active task definition ARN from service:**

**CLI:**
```bash
aws ecs describe-services \
  --cluster <cluster-name> \
  --services <service-name> \
  --query 'services[0].taskDefinition' \
  --output text
```

**Example output:**
```
arn:aws:ecs:us-east-1:123456789012:task-definition/my-app:7
```

**Step 2 — Describe the task definition for roles:**

**CLI:**
```bash
aws ecs describe-task-definition \
  --task-definition <task-definition-arn> \
  --query 'taskDefinition.{taskRoleArn:taskRoleArn,executionRoleArn:executionRoleArn}'
```

**Example output (both roles configured):**
```json
{
  "taskRoleArn": "arn:aws:iam::123456789012:role/my-app-task-role",
  "executionRoleArn": "arn:aws:iam::123456789012:role/ecsTaskExecutionRole"
}
```

**Example output (task role not configured):**
```json
{
  "taskRoleArn": null,
  "executionRoleArn": "arn:aws:iam::123456789012:role/ecsTaskExecutionRole"
}
```

**Interpret the result:**
- `taskRoleArn` present → report the full ARN
- `taskRoleArn` is `null` or absent → report `"not_configured"`
- `executionRoleArn` present → report the full ARN
- `executionRoleArn` is `null` or absent → report `"not_configured"`

### 2. Secrets References

Secrets are defined in the `secrets` array within each container definition of the task definition. Each secret has a `name` (the environment variable name in the container) and a `valueFrom` (the ARN or parameter name to resolve).

**CLI:**
```bash
aws ecs describe-task-definition \
  --task-definition <task-definition-arn> \
  --query 'taskDefinition.containerDefinitions[].{containerName:name,secrets:secrets}'
```

**Example output (secrets configured):**
```json
[
  {
    "containerName": "app",
    "secrets": [
      {
        "name": "DB_PASSWORD",
        "valueFrom": "arn:aws:secretsmanager:us-east-1:123456789012:secret:prod/db-password-AbCdEf"
      },
      {
        "name": "API_KEY",
        "valueFrom": "arn:aws:ssm:us-east-1:123456789012:parameter/prod/api-key"
      }
    ]
  },
  {
    "containerName": "sidecar",
    "secrets": [
      {
        "name": "CONFIG_TOKEN",
        "valueFrom": "/prod/config-token"
      }
    ]
  }
]
```

**Example output (no secrets):**
```json
[
  {
    "containerName": "app",
    "secrets": null
  }
]
```

**Interpret the result:**
- Each entry in `secrets` array → one secret reference to report
- `name` field → the `secret_name` in the output schema
- `valueFrom` field → the `value_from` in the output schema

**Source classification from `valueFrom`:**
- Starts with `arn:aws:secretsmanager:` → source is `"secrets_manager"`
- Starts with `arn:aws:ssm:` → source is `"ssm_parameter_store"`
- Does NOT start with `arn:` (plain parameter name like `/prod/config-token`) → source is `"ssm_parameter_store"`

### 3. ECS Exec Enablement

ECS Exec allows operators to run commands in or get a shell into a running container. The `enableExecuteCommand` field on the service controls whether this capability is available.

**CLI:**
```bash
aws ecs describe-services \
  --cluster <cluster-name> \
  --services <service-name> \
  --query 'services[0].enableExecuteCommand'
```

**Example output (enabled):**
```
true
```

**Example output (disabled):**
```
false
```

**Interpret the result:**
- `true` → report `enable_execute_command: true`
- `false` or field absent → report `enable_execute_command: false`

---

## Output Schema

```yaml
security:
  services:
    - service_name: string
      task_role_arn: string | "not_configured"
      execution_role_arn: string | "not_configured"
      enable_execute_command: bool  # service-level flag only; full Exec functionality also requires SSM permissions (task role, or EC2 instance role) and a writable root filesystem
      error: string | null          # Set when a describe call failed for this service; other fields may be absent
      secrets:
        - container_name: string
          secret_name: string
          source: string          # "secrets_manager" | "ssm_parameter_store"
          value_from: string      # ARN or parameter name
```

**Field descriptions:**
- `task_role_arn` — the IAM role ARN containers assume at runtime, or `"not_configured"` if not set
- `execution_role_arn` — the IAM role ARN the ECS agent uses for image pulls and log publishing, or `"not_configured"` if not set
- `enable_execute_command` — whether the service-level ECS Exec flag is set (`true` or `false`); mirrors the `enableExecuteCommand` API field and does not by itself prove Exec is functional
- `error` — `null` on success; when a describe call fails for this service, records the failing API call and error code
- `secrets` — list of secrets injected into containers; empty list `[]` when no secrets are configured
- `source` — classification of the secret backend: `"secrets_manager"` or `"ssm_parameter_store"`
- `value_from` — the original ARN or parameter name as declared in the task definition

---

## Edge Cases

Handle these scenarios to ensure accurate security posture reporting.

### No task role configured

When `taskRoleArn` is null or absent from the task definition, containers run without an assumed IAM role. Execution-role permissions are not directly accessible by the containers in the task; on the EC2 launch type, containers may still obtain credentials from the container instance's IAM role via the instance metadata service.

**How to handle:**
- Report `task_role_arn: "not_configured"`
- Do NOT fail the module — this is a valid (though not recommended) configuration

**Example output:**
```yaml
security:
  services:
    - service_name: legacy-worker
      task_role_arn: "not_configured"
      execution_role_arn: "arn:aws:iam::123456789012:role/ecsTaskExecutionRole"
      enable_execute_command: false
      error: null
      secrets: []
```

### No execution role configured

When `executionRoleArn` is null or absent, on Fargate and Managed Instances the ECS agent cannot pull images from private ECR repositories or publish logs on behalf of the task. On the EC2 launch type, the container instance's IAM role covers image pulls and log publishing, so a missing execution role is common there (e.g., with public images).

**How to handle:**
- Report `execution_role_arn: "not_configured"`
- Do NOT fail the module — the task may still function with public images and no logging

### No secrets configured

When no container definitions have entries in their `secrets` array (all are null or empty), report an empty secrets list.

**How to handle:**
- Report `secrets: []` (empty list)
- Do NOT omit the `secrets` key — always include it for schema consistency

### Secrets Manager vs SSM Parameter Store classification

> Facts verified 2026-07-14 against https://docs.aws.amazon.com/AmazonECS/latest/developerguide/specifying-sensitive-data.html

The `valueFrom` field determines the source classification. Apply these rules:

| `valueFrom` pattern | Source classification |
|---------------------|----------------------|
| `arn:aws:secretsmanager:*` | `"secrets_manager"` |
| `arn:aws:ssm:*` (full ARN) | `"ssm_parameter_store"` |
| No `arn:` prefix (e.g., `/prod/my-param`) | `"ssm_parameter_store"` |

**Why plain names are SSM Parameter Store:**
ECS allows specifying SSM parameters by name (with or without leading `/`) as shorthand. Secrets Manager values always require the full ARN. Therefore, any `valueFrom` value that does not start with `arn:` is an SSM Parameter Store reference by convention.

**Example with mixed sources:**
```yaml
secrets:
  - container_name: app
    secret_name: DB_PASSWORD
    source: secrets_manager
    value_from: "arn:aws:secretsmanager:us-east-1:123456789012:secret:prod/db-password-AbCdEf"
  - container_name: app
    secret_name: API_KEY
    source: ssm_parameter_store
    value_from: "arn:aws:ssm:us-east-1:123456789012:parameter/prod/api-key"
  - container_name: sidecar
    secret_name: CONFIG_TOKEN
    source: ssm_parameter_store
    value_from: "/prod/config-token"
```

### ECS Exec requires service enablement and task role permissions

For ECS Exec to be fully functional, three conditions must be met:
1. The service must have `enableExecuteCommand: true`
2. The IAM role providing SSM Session Manager permissions must be in place — normally the task role; on the EC2 launch type, if no task role is configured, the container instance's IAM role is used instead, so the absence of a task role does not by itself mean Exec is non-functional
3. The container must have a writable root filesystem (`readonlyRootFilesystem` must not be `true`)

**How to handle in this module:**
- Report **only** the service-level `enableExecuteCommand` field as `enable_execute_command`
- This module reports what is configured at the service/task-definition level, not whether all runtime prerequisites are met
- The service-level flag is the primary indicator from `ecs:DescribeServices`

### Task definition or service retrieval fails

If `ecs:DescribeTaskDefinition` or `ecs:DescribeServices` returns an error for a specific service:

**How to handle:**
- Record the error on that service's entry (set `error` to the failing API call and error code) and continue with the remaining services — one inaccessible service must not discard data for the others
- Do NOT present the errored service's partial data as complete — omit fields you could not retrieve
- Use module-level `unavailable: true` ONLY when the module cannot produce any data at all (every service failed, or a prerequisite call failed before any per-service data was gathered)

**Example — one service failed, others succeeded:**
```yaml
security:
  services:
    - service_name: my-app
      error: "ecs:DescribeTaskDefinition failed for 'my-app:7': AccessDeniedException"
    - service_name: healthy-service
      task_role_arn: "arn:aws:iam::123456789012:role/healthy-task-role"
      execution_role_arn: "arn:aws:iam::123456789012:role/ecsTaskExecutionRole"
      enable_execute_command: false
      error: null
      secrets: []
```

**Example — total failure only:**
```yaml
security:
  unavailable: true
  reason: "ecs:DescribeServices failed for all requested services: AccessDeniedException"
```

### Multiple containers with secrets

A task definition may have multiple containers (app + sidecars), each with their own secrets. Report secrets per container to maintain traceability.

**Example:**
```yaml
secrets:
  - container_name: app
    secret_name: DB_PASSWORD
    source: secrets_manager
    value_from: "arn:aws:secretsmanager:us-east-1:123456789012:secret:prod/db-password-AbCdEf"
  - container_name: datadog-agent
    secret_name: DD_API_KEY
    source: secrets_manager
    value_from: "arn:aws:secretsmanager:us-east-1:123456789012:secret:shared/datadog-api-key-XyZ123"
```

---

## Sources

- Task execution IAM role (execution-role permissions are not directly accessible by containers): https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_execution_IAM_role.html
- Task IAM role: https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-iam-roles.html
- ECS Exec prerequisites (including EC2 instance-role fallback when no task role is set): https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-exec.html
- Passing sensitive data to containers (Secrets Manager vs SSM Parameter Store `valueFrom` forms): https://docs.aws.amazon.com/AmazonECS/latest/developerguide/specifying-sensitive-data.html
