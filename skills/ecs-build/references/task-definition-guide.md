# Task Definition Guide

> **Part of:** [ecs-build](../SKILL.md)

Generating `aws_ecs_task_definition` (or the container-definition submodule) correctly.

> Facts verified 2026-07-10 against https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/ecs_task_definition, https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_execution_IAM_role.html, https://docs.aws.amazon.com/AmazonECS/latest/developerguide/fargate-tasks-services.html, and https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-account-settings.html

## Execution role vs task role (Critical Rule 5)

| | Execution role (`execution_role_arn`) | Task role (`task_role_arn`) |
|---|---|---|
| Used by | ECS container agent / Fargate agent | Your application code (SDK/CLI in containers) |
| Typical permissions | ECR pull, awslogs, `ssm:GetParameters` / `secretsmanager:GetSecretValue` / `kms:Decrypt` for secrets | S3/DynamoDB/SQS/... whatever the app calls |
| Managed policy | `arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy` | None -- least-privilege custom policy per service |
| Trust principal | `ecs-tasks.amazonaws.com` | `ecs-tasks.amazonaws.com` |

- Execution role is required on Fargate, Managed Instances, and external instances for private-ECR pulls and awslogs.
- `ecr:GetAuthorizationToken` requires `Resource: "*"` -- do not try to scope it.
- ECS Exec permissions (`ssmmessages:*`) go on the **task** role, not the execution role.
- Trust-policy scoping (account-wide `aws:SourceArn` wildcard, never cluster-scoped): see [networking-security.md](networking-security.md).
- One role pair per service, not one shared pair per cluster.

## Secrets injection

```jsonc
"secrets": [
  { "name": "DB_PASSWORD", "valueFrom": "arn:aws:secretsmanager:<region>:<acct>:secret:<name>-AbCdEf" },
  // Specific JSON key inside the secret — note the ARN suffix format
  // arn:...:secret:<name>-AbCdEf:<json-key>:<version-stage>:<version-id>
  // Trailing colons are REQUIRED when omitting version-stage/version-id:
  { "name": "DB_USER", "valueFrom": "arn:aws:secretsmanager:<region>:<acct>:secret:<name>-AbCdEf:username::" }
]
```

- **The `:json-key::` suffix gotcha:** to extract one key from a JSON secret, append `:<json-key>:<version-stage>:<version-id>` to the secret ARN; leave version fields empty but keep the colons (`:username::`). Dropping the trailing colons makes ECS treat the whole string as a nonexistent secret ARN. Source: https://docs.aws.amazon.com/AmazonECS/latest/developerguide/secrets-envvar-secrets-manager.html (verified 2026-07-10).
- **Never put secret values in the plain `environment` map** -- they land in the task definition (visible via DescribeTaskDefinition, console, state files). Always `secrets`/`valueFrom`. Anti-pattern: `"environment": [{"name": "DB_PASSWORD", "value": "hunter2"}]`.
- Values are injected at container start only -- secret rotation requires a new deployment to pick up.
- Execution-role additions: `secretsmanager:GetSecretValue` (Secrets Manager), `ssm:GetParameters` (Parameter Store), `kms:Decrypt` (customer-managed keys only).
- Private subnets need the matching `secretsmanager` / `ssm` / `kms` VPC endpoints (Critical Rule 8).

## awslogs mode (Critical Rule 4)

- On **2025-06-25** ECS changed the default log driver mode from `blocking` to `non-blocking` (prioritizing task availability over log delivery), governed per-account by the `defaultLogDriverMode` account setting. An explicit `mode` in `logConfiguration.options` always wins -- so generated code **always sets it explicitly**.
- Trade-off to state in the README:
  - `"mode": "non-blocking"` + `"max-buffer-size": "25m"` -- task keeps running if CloudWatch is unreachable; logs may be **dropped** when the buffer fills. Default for availability-first services.
  - `"mode": "blocking"` -- guaranteed delivery; stdout writes **block** (and can wedge the app) if CloudWatch is unreachable. Use for audit-grade logging only, with the justification recorded (the validator flags unjustified blocking mode).
- Source: https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-account-settings.html (verified 2026-07-10).

## FireLens (routing beyond CloudWatch)

When the destination is Firehose/Datadog/Splunk/OpenSearch etc. (or awslogs' feature set is insufficient), render FireLens instead of awslogs -- destination/stack *selection* belongs to `ecs-observability`; this skill renders the chosen config:

```jsonc
// sidecar container
{ "name": "fluent-bit",
  "image": "<region-specific aws-for-fluent-bit image, resolve via SSM /aws/service/aws-for-fluent-bit/stable>",
  "essential": true,
  "firelensConfiguration": { "type": "fluentbit" } },
// app container
{ "name": "app",
  "logConfiguration": {
    "logDriver": "awsfirelens",
    "options": { "Name": "firehose", "region": "<region>", "delivery_stream": "<stream>" } } }
```

- Task role (not execution role) needs write permissions to the destination (e.g. `firehose:PutRecordBatch`).
- SaaS destinations (Datadog, Splunk, ...) must receive API keys via `secretOptions`/`valueFrom`, never inline in `options` -- inline keys land in the task definition in plaintext.
- Give the fluent-bit container its own awslogs config so the router's own logs are captured.
- Working end-to-end example: https://github.com/terraform-aws-modules/terraform-aws-ecs/tree/master/examples/complete (fluent-bit sidecar + `awsfirelens` driver, verified 2026-07-10).

## runtime_platform and Graviton

```hcl
runtime_platform {
  cpu_architecture        = "ARM64"   # Graviton; or "X86_64"
  operating_system_family = "LINUX"
}
```

- ARM64 is Linux-only. Windows on Fargate requires X86_64 and >= 1 vCPU (families: Windows Server 2019/2022 Full/Core).
- Managed Instances: Bottlerocket, X86_64 or ARM64, Linux containers only.
- Confirm the image is multi-arch (or arm64) before defaulting to Graviton.

## Fargate-specific constraints (Critical Rule 10)

- **Invalid parameters on Fargate:** `disableNetworking`, `dnsSearchDomains`, `dnsServers`, `dockerSecurityOptions`, `extraHosts`, `gpu`, `ipcMode`, `links`, `placementConstraints`, `privileged`, `maxSwap`, `swappiness`.
- `linuxParameters.capabilities`: the only addable capability is `CAP_SYS_PTRACE`; `devices`, `sharedMemorySize`, `tmpfs` unsupported.
- **No GPUs on Fargate** (as of 2026-07-10, per the exclusion list above) -- GPU workloads go to EC2 or Managed Instances capacity (design via `ecs-genai`).
- Task-level CPU/memory required, fixed combos: 256 (.25 vCPU)/512MiB-2GB up to 32768 (32 vCPU)/60-244GB; 8+ vCPU requires Linux platform 1.4.0+.
- Volumes: bind mounts, EFS, EBS, S3 Files -- no `dockerVolumeConfiguration`.
- **ephemeral_storage:** `size_in_gib` 21-200 (Fargate; 20 GiB free baseline, billed above -- https://docs.aws.amazon.com/AmazonECS/latest/developerguide/fargate-task-storage.html).
- **SOCI lazy loading is Fargate-only, Linux platform version 1.4.0 only** -- gzip/uncompressed images in ECR private, index alongside the image; recommend for images > 250 MiB. Not available on EC2 or MI (those pull full images via the AMI's runtime). **New adopters can only use SOCI Index Manifest v2** (v1 is grandfathered for existing users; migrate). Source: https://docs.aws.amazon.com/AmazonECS/latest/developerguide/fargate-tasks-services.html (verified 2026-07-10).

## EBS task volumes

Task definition declares the volume with `configure_at_launch = true`; the EBS settings live on the **service**:

```hcl
# in aws_ecs_task_definition
volume {
  name                = "data"
  configure_at_launch = true
}

# in aws_ecs_service
volume_configuration {
  name = "data"
  managed_ebs_volume {
    role_arn         = aws_iam_role.ecs_infrastructure_volumes.arn # REQUIRED
    size_in_gb       = 100
    file_system_type = "xfs"    # default; ext3/ext4 also valid
    encrypted        = true      # default
    # iops, throughput, volume_type, kms_key_id, snapshot_id, volume_initialization_rate
  }
}
```

- The role is the **infrastructure role** with `arn:aws:iam::aws:policy/service-role/AmazonECSInfrastructureRolePolicyForVolumes` (note: this one IS under `service-role/`, unlike the Managed Instances policy).
- EBS task volumes require the `ECS` deployment controller.
- **Never delete/modify the infrastructure role while EBS-volume tasks run** -- tasks get stuck in `DEPROVISIONING`. Add a comment in generated code. **Recovery:** restore the role (or recreate it with the same name, `ecs.amazonaws.com` trust, and the Volumes policy -- at minimum `ec2:DetachVolume`/`DeleteVolume`/`DescribeVolumes`); ECS retries automatically at regular intervals and the stuck stop/delete then completes (https://docs.aws.amazon.com/AmazonECS/latest/developerguide/infrastructure_IAM_role.html, verified 2026-07-10).

## EFS volumes (persistent shared storage)

Unlike EBS, EFS config lives entirely on the **task definition** volume block; the filesystem + access point are ordinary resources:

```hcl
volume {
  name = "shared"
  efs_volume_configuration {
    file_system_id     = aws_efs_file_system.this.id
    transit_encryption = "ENABLED"           # always -- required for IAM auth
    authorization_config {
      access_point_id = aws_efs_access_point.this.id
      iam             = "ENABLED"            # task-role-based authorization
    }
  }
}
```

- Prefer **access points** (enforced POSIX user + root directory) over raw filesystem mounts; with `iam = "ENABLED"` the task role needs `elasticfilesystem:ClientMount`/`ClientWrite` on the filesystem.
- **`root_directory` is ignored when `authorization_config` sets an access point** -- set the root directory on the access point itself (provider docs).
- Security groups: allow **NFS TCP 2049** from the task security group to the EFS mount-target security group.
- Private VPCs: a **mount target must be reachable in each AZ the tasks run in** -- missing mount targets surface as task-start timeouts, not clear errors.
- Sources: https://docs.aws.amazon.com/AmazonECS/latest/developerguide/efs-volumes.html · https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/ecs_task_definition (verified 2026-07-10).

## S3 Files volumes (direct file access to S3)

S3 Files mounts an S3-backed file system into tasks via `s3files_volume_configuration` on the task-definition `volume` block (provider >= 6.41.0): `file_system_arn` (required, `arn:...:s3files:...:file-system/fs-xxxxx`), optional `access_point_arn`, `root_directory`, `transit_encryption_port`. Transit encryption and a task IAM role are **mandatory and auto-enforced**; the task role needs permissions to connect to the file system and read the S3 objects. Launch types: **Fargate and Managed Instances only -- tasks fail at launch on the EC2 launch type** as of 2026-07-10. Source: https://docs.aws.amazon.com/AmazonECS/latest/developerguide/s3files-volumes.html (verified 2026-07-10).

## Other

- `requires_compatibilities` valid values: `EC2`, `FARGATE`, `EXTERNAL`, `MANAGED_INSTANCES` -- include the one(s) matching the capacity model, `MANAGED_INSTANCES` mandatory for MI tasks.
- `track_latest = true` only when deployments happen outside Terraform (CI pipelines registering revisions) -- otherwise leave default to avoid perpetual diffs.
- Container `dependsOn` with `condition = "HEALTHY"` requires a health check on the dependency, or startup blocks forever; use `SUCCESS` for init containers.

## Sources

- https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/ecs_task_definition
- https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_execution_IAM_role.html · https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-iam-roles.html
- https://docs.aws.amazon.com/AmazonECS/latest/developerguide/secrets-envvar-secrets-manager.html · https://docs.aws.amazon.com/AmazonECS/latest/developerguide/secrets-envvar-ssm-paramstore.html
- https://docs.aws.amazon.com/AmazonECS/latest/developerguide/fargate-tasks-services.html · https://docs.aws.amazon.com/AmazonECS/latest/developerguide/fargate-task-storage.html · https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-account-settings.html
- https://docs.aws.amazon.com/AmazonECS/latest/developerguide/efs-volumes.html · https://docs.aws.amazon.com/AmazonECS/latest/developerguide/s3files-volumes.html · https://github.com/terraform-aws-modules/terraform-aws-ecs/tree/master/examples/complete (FireLens)
- https://docs.aws.amazon.com/AmazonECS/latest/developerguide/infrastructure_IAM_role.html
- JSON-key colon gotcha and dependsOn framing: aws/agent-toolkit-for-aws `aws-containers` skill, Gotchas 4, 18 (Apache-2.0, retrieved 2026-07-10)
